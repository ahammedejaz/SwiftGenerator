"""Azure OpenAI and OpenAI-compatible structured completions.

The organisation-approved endpoint is an Azure OpenAI resource; the same code serves any
server that speaks the OpenAI ``/chat/completions`` contract. It reuses the OpenRouter
client's response parsing, usage accounting, retry schedule and error mapping — the wire
format is the same — and differs only in where the request goes, how it authenticates, and
in dropping OpenRouter's routing block, which no other provider understands.

Verified against the Azure documentation current at implementation time (May 2026
revision): the ``v1`` surface ``/openai/v1/chat/completions`` needs no ``api-version``,
takes the deployment name in ``model`` and authenticates with an ``api-key`` header. The
legacy ``/openai/deployments/{deployment}/chat/completions?api-version=…`` surface is still
GA, so it is the fallback when the v1 route answers 404 (an older resource or a proxy).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import httpx

from app.agents.errors import AiServiceError, ai_error
from app.agents.providers.base import (
    InterpretationModelRequest,
    InterpretationModelResponse,
    StructuredCompletionRequest,
    StructuredCompletionResponse,
)
from app.agents.providers.openrouter import OpenRouterClient
from app.config import Settings

Sleep = Callable[[float], Awaitable[None]]


class OpenAiCompatibleClient(OpenRouterClient):
    """Structured completions against Azure OpenAI or an OpenAI-compatible endpoint."""

    provider_name = "azure_openai"

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._random = random_source
        self._owns_client = http_client is None
        self._azure = settings.ai_endpoint_is_azure
        self.provider_name = "azure_openai" if self._azure else "openai_compatible"
        #: Once the v1 route has answered 404 we stop trying it for this process.
        self._legacy_only = False
        timeout = httpx.Timeout(
            settings.openrouter_timeout_seconds,
            connect=settings.openrouter_connect_timeout_seconds,
        )
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.ai_endpoint_origin or "https://invalid.invalid",
            timeout=timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    # -- configuration ---------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.ai_endpoint_origin
            and self._settings.ai_api_key
            and self._settings.ai_api_key.get_secret_value()
            and self._settings.ai_chat_deployment
        )

    @property
    def deployment(self) -> str:
        return self._settings.ai_chat_deployment

    def build_headers(self) -> dict[str, str]:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        assert self._settings.ai_api_key is not None
        secret = self._settings.ai_api_key.get_secret_value()
        headers = {"Content-Type": "application/json"}
        if self._azure:
            headers["api-key"] = secret
        else:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _routes(self) -> list[tuple[str, dict[str, str]]]:
        """Candidate ``(path, query)`` pairs in the order they are tried."""
        if not self._azure:
            return [("/v1/chat/completions", {}), ("/chat/completions", {})]
        legacy = (
            f"/openai/deployments/{self.deployment}/chat/completions",
            {"api-version": self._settings.ai_api_version_effective},
        )
        if self._legacy_only:
            return [legacy]
        return [("/openai/v1/chat/completions", {}), legacy]

    # -- payloads --------------------------------------------------------------------

    def build_payload(self, request: InterpretationModelRequest) -> dict[str, Any]:
        payload = super().build_payload(request)
        payload.pop("provider", None)
        payload["model"] = self.deployment
        return payload

    def build_completion_payload(self, request: StructuredCompletionRequest) -> dict[str, Any]:
        payload = super().build_completion_payload(request)
        payload.pop("provider", None)
        # The deployment is the model. A caller's pinned OpenRouter slug would be rejected by
        # Azure, so it is ignored here rather than forwarded.
        payload["model"] = self.deployment
        return payload

    # -- transport -------------------------------------------------------------------

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        """Try the v1 surface, then the legacy one; remember which answered."""
        routes = self._routes()
        response: httpx.Response | None = None
        for index, (path, params) in enumerate(routes):
            response = await self._client.post(
                path, params=params or None, headers=self.build_headers(), json=payload
            )
            if response.status_code == 404 and index + 1 < len(routes):
                if self._azure and index == 0:
                    self._legacy_only = True
                continue
            return response
        assert response is not None
        return response

    async def interpret(
        self,
        request: InterpretationModelRequest,
    ) -> InterpretationModelResponse:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        started = monotonic()
        last_error: AiServiceError | None = None
        max_attempts = self._settings.openrouter_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._post(self.build_payload(request))
                parsed = self._parse_response(response, attempt, started)
                return InterpretationModelResponse(
                    payload=parsed.payload,
                    model=parsed.model or self.deployment,
                    attempt_count=parsed.attempt_count,
                    latency_ms=parsed.latency_ms,
                    usage=parsed.usage,
                    provider=self.provider_name,
                    http_status=parsed.http_status,
                )
            except httpx.TimeoutException:
                last_error = ai_error(
                    "AI_TIMEOUT", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except httpx.NetworkError:
                last_error = ai_error(
                    "AI_PROVIDER_UNAVAILABLE", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except AiServiceError as exc:
                last_error = exc.with_attempt_count(attempt)
            if last_error is None or not last_error.retryable or attempt >= max_attempts:
                assert last_error is not None
                raise last_error
            await self._sleep(self._retry_delay(attempt, last_error.retry_after))
        assert last_error is not None
        raise last_error

    async def complete(self, request: StructuredCompletionRequest) -> StructuredCompletionResponse:
        if not self.configured:
            raise ai_error("AI_NOT_CONFIGURED")
        started = monotonic()
        last_error: AiServiceError | None = None
        max_attempts = self._settings.openrouter_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._post(self.build_completion_payload(request))
                parsed = self._parse_response(response, attempt, started)
                return StructuredCompletionResponse(
                    payload=parsed.payload,
                    model=parsed.model or self.deployment,
                    attempt_count=parsed.attempt_count,
                    latency_ms=parsed.latency_ms,
                    usage=parsed.usage,
                    provider=self.provider_name,
                    http_status=parsed.http_status,
                )
            except httpx.TimeoutException:
                last_error = ai_error(
                    "AI_TIMEOUT", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except httpx.NetworkError:
                last_error = ai_error(
                    "AI_PROVIDER_UNAVAILABLE", retryable=True, affects_circuit=True
                ).with_attempt_count(attempt)
            except AiServiceError as exc:
                last_error = exc.with_attempt_count(attempt)
            if last_error is None or not last_error.retryable or attempt >= max_attempts:
                assert last_error is not None
                raise last_error
            await self._sleep(self._retry_delay(attempt, last_error.retry_after))
        assert last_error is not None
        raise last_error


def structured_client(settings: Settings) -> OpenRouterClient | None:
    """The configured structured-completion provider for the AI authoring paths, or None.

    ``None`` means disabled or unconfigured and is reported as such; it is never replaced
    by a scripted client pretending to be live.
    """
    effective = settings.structured_ai_provider_effective
    client: OpenRouterClient | None = None
    if effective in {"azure_openai", "openai_compatible"}:
        client = OpenAiCompatibleClient(settings)
    elif effective == "openrouter":
        client = OpenRouterClient(settings)
    return client if client is not None and client.configured else None
