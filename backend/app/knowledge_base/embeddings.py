"""Provider-neutral embeddings.

``EmbeddingProvider.embed(texts)`` returns vectors plus usage. One live implementation
serves Azure OpenAI and any OpenAI-compatible ``/embeddings`` endpoint; a deterministic fake
serves CI; a disabled provider says so. Batching, retry with backoff, ``Retry-After``,
timeouts and partial retry live here once. No implementation logs text.

Azure surfaces, verified against the documentation current at implementation time: the
``v1`` route ``/openai/v1/embeddings`` (deployment in ``model``, no ``api-version``) and the
legacy ``/openai/deployments/{deployment}/embeddings?api-version=…`` route. v1 is tried first
and the legacy route is used from the first 404 onwards.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import Settings

RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
MAX_INPUT_CHARS = 24_000


@dataclass(frozen=True)
class EmbeddingUsage:
    prompt_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    dimensions: int
    model: str
    provider: str
    usage: EmbeddingUsage
    latency_ms: int
    requests: int
    attempts: int = 1


class EmbeddingError(Exception):
    def __init__(self, code: str, detail: str, *, status: int | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


class EmbeddingProvider(Protocol):
    name: str
    deployment: str

    @property
    def available(self) -> bool: ...

    def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...


@dataclass
class DisabledEmbeddingProvider:
    name: str = "disabled"
    deployment: str = ""
    reason: str = "EMBEDDING_PROVIDER_UNAVAILABLE"

    @property
    def available(self) -> bool:
        return False

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        raise EmbeddingError(self.reason, "no embedding provider is configured")


@dataclass
class FakeEmbeddingProvider:
    """Deterministic vectors from a hash of the text. Good enough to prove batching, caching,
    filtering and fusion; nothing about it is semantic and nothing leaves the process."""

    dimensions: int = 256
    name: str = "fake"
    deployment: str = "fake-embedding-v1"
    fail_on: frozenset[str] = frozenset()
    calls: list[int] = field(default_factory=list)
    #: Raise a retryable error this many times before succeeding — exercises retry paths.
    transient_failures: int = 0

    @property
    def available(self) -> bool:
        return True

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls.append(len(texts))
        if self.transient_failures > 0:
            self.transient_failures -= 1
            raise EmbeddingError("EMBEDDING_RATE_LIMITED", "simulated 429", status=429)
        vectors: list[list[float]] = []
        for text in texts:
            if text in self.fail_on:
                raise EmbeddingError("EMBEDDING_PROVIDER_UNAVAILABLE", "simulated failure")
            vectors.append(_hash_vector(text, self.dimensions))
        tokens = sum(max(1, len(text) // 4) for text in texts)
        return EmbeddingResult(
            vectors=vectors,
            dimensions=self.dimensions,
            model=self.deployment,
            provider=self.name,
            usage=EmbeddingUsage(prompt_tokens=tokens, total_tokens=tokens),
            latency_ms=0,
            requests=1,
        )


def _hash_vector(text: str, dimensions: int) -> list[float]:
    """A bag-of-words-ish projection so similar texts land near each other: every token
    contributes a hashed direction. Deterministic across processes."""
    vector = [0.0] * dimensions
    tokens = text.lower().split() or [text.lower()]
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        for offset in range(0, min(len(digest), 32), 2):
            index = int.from_bytes(digest[offset : offset + 2], "big") % dimensions
            vector[index] += 1.0 if digest[offset] % 2 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class OpenAiCompatibleEmbeddingProvider:
    """Azure OpenAI or OpenAI-compatible embeddings over httpx."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleep: object | None = None,
    ) -> None:
        self._settings = settings
        self._azure = settings.ai_endpoint_is_azure
        self.name = "azure_openai" if self._azure else "openai_compatible"
        self.deployment = settings.embeddings_deployment
        self._legacy_only = False
        self._client = client or httpx.Client(
            base_url=settings.ai_endpoint_origin or "https://invalid.invalid",
            timeout=httpx.Timeout(settings.embedding_timeout_seconds, connect=5.0),
        )
        self._sleep = sleep if callable(sleep) else time.sleep

    @property
    def available(self) -> bool:
        return bool(
            self._settings.ai_endpoint_origin
            and self._settings.ai_api_key
            and self._settings.ai_api_key.get_secret_value()
            and self.deployment
        )

    def _headers(self) -> dict[str, str]:
        assert self._settings.ai_api_key is not None
        secret = self._settings.ai_api_key.get_secret_value()
        if self._azure:
            return {"api-key": secret, "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    def _routes(self) -> list[tuple[str, dict[str, str], bool]]:
        """``(path, query, model_in_body)`` in the order tried."""
        if not self._azure:
            return [("/v1/embeddings", {}, True), ("/embeddings", {}, True)]
        legacy = (
            f"/openai/deployments/{self.deployment}/embeddings",
            {"api-version": self._settings.ai_api_version_effective},
            False,
        )
        if self._legacy_only:
            return [legacy]
        return [("/openai/v1/embeddings", {}, True), legacy]

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        if not self.available:
            raise EmbeddingError(
                "EMBEDDING_PROVIDER_UNAVAILABLE", "embedding endpoint not configured"
            )
        if not texts:
            return EmbeddingResult([], 0, self.deployment, self.name, EmbeddingUsage(), 0, 0)
        started = time.monotonic()
        vectors: list[list[float]] = []
        prompt_tokens = 0
        total_tokens = 0
        usage_seen = False
        requests = 0
        attempts = 0
        batch_size = max(1, self._settings.embedding_batch_size)
        for start in range(0, len(texts), batch_size):
            batch = [text[:MAX_INPUT_CHARS] for text in texts[start : start + batch_size]]
            body, used, tried = self._embed_batch(batch)
            requests += used
            attempts += tried
            vectors.extend(body)
            usage = self._last_usage
            if usage is not None:
                usage_seen = True
                prompt_tokens += usage.prompt_tokens or 0
                total_tokens += usage.total_tokens or 0
        dimensions = len(vectors[0]) if vectors else 0
        if any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingError(
                "EMBEDDING_DIMENSION_MISMATCH", "the provider returned mixed vector lengths"
            )
        return EmbeddingResult(
            vectors=vectors,
            dimensions=dimensions,
            model=self._last_model or self.deployment,
            provider=self.name,
            usage=(
                EmbeddingUsage(prompt_tokens=prompt_tokens, total_tokens=total_tokens)
                if usage_seen
                else EmbeddingUsage()
            ),
            latency_ms=round((time.monotonic() - started) * 1000),
            requests=requests,
            attempts=attempts,
        )

    _last_usage: EmbeddingUsage | None = None
    _last_model: str | None = None

    def _embed_batch(self, batch: list[str]) -> tuple[list[list[float]], int, int]:
        payload: dict[str, object] = {"input": list(batch)}
        if self._settings.embedding_dimensions:
            payload["dimensions"] = self._settings.embedding_dimensions
        max_attempts = max(1, self._settings.embedding_max_retries + 1)
        last_error: EmbeddingError | None = None
        requests = 0
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._post(payload)
                requests += 1
            except httpx.TimeoutException as error:
                last_error = EmbeddingError("EMBEDDING_TIMEOUT", "the embedding request timed out")
                del error
            except httpx.HTTPError as error:
                last_error = EmbeddingError("EMBEDDING_PROVIDER_UNAVAILABLE", type(error).__name__)
            else:
                if response.status_code < 400:
                    return self._parse(response, len(batch)), requests, attempt
                last_error = self._error_for(response)
                if response.status_code not in RETRYABLE_STATUSES:
                    raise last_error
                retry_after = _retry_after(response)
                if attempt < max_attempts:
                    self._sleep(
                        retry_after if retry_after is not None else min(2.0**attempt * 0.25, 8.0)
                    )
                continue
            if attempt < max_attempts:
                self._sleep(min(2.0**attempt * 0.25, 8.0))
        assert last_error is not None
        raise last_error

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        routes = self._routes()
        response: httpx.Response | None = None
        for index, (path, params, model_in_body) in enumerate(routes):
            body = dict(payload)
            if model_in_body:
                body["model"] = self.deployment
            response = self._client.post(
                path, params=params or None, headers=self._headers(), json=body
            )
            if response.status_code == 404 and index + 1 < len(routes):
                if self._azure and index == 0:
                    self._legacy_only = True
                continue
            return response
        assert response is not None
        return response

    def _parse(self, response: httpx.Response, expected: int) -> list[list[float]]:
        try:
            body = response.json()
        except ValueError as error:
            raise EmbeddingError("EMBEDDING_PROVIDER_UNAVAILABLE", "non-JSON body") from error
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != expected:
            raise EmbeddingError(
                "EMBEDDING_PROVIDER_UNAVAILABLE",
                f"expected {expected} vectors, received "
                f"{len(data) if isinstance(data, list) else 'none'}",
            )
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors: list[list[float]] = []
        for item in ordered:
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("EMBEDDING_PROVIDER_UNAVAILABLE", "an empty vector")
            vectors.append([float(value) for value in vector])
        usage = body.get("usage") if isinstance(body, dict) else None
        self._last_usage = (
            EmbeddingUsage(
                prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
                total_tokens=_int_or_none(usage.get("total_tokens")),
            )
            if isinstance(usage, dict)
            else None
        )
        model = body.get("model") if isinstance(body, dict) else None
        self._last_model = model if isinstance(model, str) else None
        return vectors

    def _error_for(self, response: httpx.Response) -> EmbeddingError:
        status = response.status_code
        code = {
            401: "EMBEDDING_AUTHENTICATION_FAILED",
            403: "EMBEDDING_AUTHENTICATION_FAILED",
            404: "EMBEDDING_DEPLOYMENT_NOT_FOUND",
            429: "EMBEDDING_RATE_LIMITED",
            408: "EMBEDDING_TIMEOUT",
            504: "EMBEDDING_TIMEOUT",
        }.get(
            status,
            "EMBEDDING_PROVIDER_UNAVAILABLE" if status >= 500 else "EMBEDDING_REQUEST_INVALID",
        )
        # Provider messages can echo request content; only the status is recorded.
        return EmbeddingError(code, f"HTTP {status}", status=status)

    def close(self) -> None:
        self._client.close()


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), 30.0)
    except ValueError:
        return None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def embedding_provider(settings: Settings) -> EmbeddingProvider:
    effective = settings.embedding_provider_effective
    if effective == "fake":
        return FakeEmbeddingProvider(dimensions=settings.embedding_dimensions or 64)
    if effective in {"azure_openai", "openai_compatible"}:
        provider = OpenAiCompatibleEmbeddingProvider(settings)
        if provider.available:
            return provider
    return DisabledEmbeddingProvider()
