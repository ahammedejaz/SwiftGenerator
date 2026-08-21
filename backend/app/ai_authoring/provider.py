"""Which structured-completion provider serves authoring, and the scripted stand-in.

``KNOWLEDGE_AI_PROVIDER``:

- ``auto`` (default) — the organisation endpoint when configured (Azure OpenAI or an
  OpenAI-compatible server), else OpenRouter when configured, else disabled.
- ``scripted`` — returns the caller's deterministic seed. Development and test only; it is
  how CI and the browser suite exercise every AI path with zero model calls.
- ``disabled``.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from app.agents.errors import AiServiceError
from app.agents.providers.base import (
    ModelUsage,
    StructuredCompletionClient,
    StructuredCompletionRequest,
    StructuredCompletionResponse,
)
from app.config import Settings, get_settings


class AiUnavailable(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class AiUsage:
    provider: str = "deterministic"
    model: str = ""
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 0
    cache_hit: bool = False
    calls_avoided: int = 0
    tokens_avoided: int = 0

    def add(self, response: StructuredCompletionResponse) -> None:
        self.llm_calls += 1
        self.prompt_tokens += response.usage.prompt_tokens
        self.completion_tokens += response.usage.completion_tokens
        self.latency_ms += response.latency_ms
        self.attempts += response.attempt_count
        self.model = response.model or self.model
        self.provider = response.provider or self.provider

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "llmCalls": self.llm_calls,
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "latencyMs": self.latency_ms,
            "attempts": self.attempts,
            "cacheHit": self.cache_hit,
            "callsAvoided": self.calls_avoided,
            "tokensAvoided": self.tokens_avoided,
            "costAvailable": False,
        }


@dataclass
class SeededClient:
    """Answers every request with the seed the caller embedded — a valid payload by
    construction. Optional overrides let a test stage a wrong answer for one role."""

    provider_name: str = "scripted"
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[StructuredCompletionRequest] = field(default_factory=list)

    async def complete(self, request: StructuredCompletionRequest) -> StructuredCompletionResponse:
        self.calls.append(request)
        payload = self.overrides.get(request.role)
        if payload is None:
            payload = _seed_from(request.user_content)
        return StructuredCompletionResponse(
            payload=payload,
            model="scripted-seed",
            attempt_count=1,
            latency_ms=0,
            usage=ModelUsage(),
            provider=self.provider_name,
        )

    async def aclose(self) -> None:
        return None


SEED_MARKER_START = "<<DETERMINISTIC_SEED>>"
SEED_MARKER_END = "<<END_DETERMINISTIC_SEED>>"


def _seed_from(user_content: str) -> dict[str, Any]:
    import json

    start = user_content.find(SEED_MARKER_START)
    end = user_content.find(SEED_MARKER_END)
    if start < 0 or end < 0:
        return {}
    raw = user_content[start + len(SEED_MARKER_START) : end].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class AuthoringProvider:
    """One structured-completion client per process, chosen from settings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: StructuredCompletionClient | None = None
        self._resolved = False
        self._lock = threading.Lock()
        self._override: StructuredCompletionClient | None = None

    @property
    def name(self) -> str:
        mode = self._settings.knowledge_ai_provider
        if mode == "scripted":
            return "scripted"
        if mode == "disabled":
            return "disabled"
        if self._settings.ai_provider == "mock":
            return "scripted"
        return self._settings.structured_ai_provider_effective

    @property
    def available(self) -> bool:
        return self.client() is not None

    def use(self, client: StructuredCompletionClient | None) -> None:
        """Tests inject a client; ``None`` restores the configured one."""
        with self._lock:
            self._override = client
            self._resolved = False
            self._client = None

    def client(self) -> StructuredCompletionClient | None:
        with self._lock:
            if self._override is not None:
                return self._override
            if not self._resolved:
                self._client = self._build()
                self._resolved = True
            return self._client

    def _build(self) -> StructuredCompletionClient | None:
        name = self.name
        if name == "disabled":
            return None
        if name == "scripted":
            if self._settings.app_env not in {"development", "test"}:
                return None
            return SeededClient()
        from app.agents.providers.openai_compatible import structured_client

        return structured_client(self._settings)

    def complete(
        self,
        *,
        role: str,
        system_prompt: str,
        user_content: str,
        schema_name: str,
        json_schema: dict[str, Any],
        usage: AiUsage,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        client = self.client()
        if client is None:
            raise AiUnavailable("AI_NOT_CONFIGURED", "no authoring provider is configured")
        request = StructuredCompletionRequest(
            role=role,
            model=self._settings.ai_chat_deployment or self._settings.openrouter_primary_model,
            system_prompt=system_prompt,
            user_content=user_content,
            schema_name=schema_name,
            json_schema=json_schema,
            max_output_tokens=max_output_tokens or self._settings.ai_max_output_tokens,
        )
        started = monotonic()
        try:
            response = _run(client.complete(request))
        except AiServiceError as error:
            raise AiUnavailable(error.code, error.safe_message) from error
        usage.add(response)
        if response.latency_ms == 0:
            usage.latency_ms += round((monotonic() - started) * 1000)
        return response.payload


class _LoopThread:
    """One event loop on one daemon thread for every provider call.

    The provider's httpx client keeps connections bound to the loop that opened them; a
    fresh ``asyncio.run`` per call would close that loop under the pool and fail the second
    request. FastAPI's sync endpoints (a threadpool) and the offline CLI both call through
    here, so the loop is created lazily and lives as long as the process.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=loop.run_forever, name="ai-authoring-loop", daemon=True
                )
                thread.start()
                self._loop = loop
            return self._loop


_LOOP = _LoopThread()


def _run(
    coroutine: Coroutine[Any, Any, StructuredCompletionResponse],
) -> StructuredCompletionResponse:
    future = asyncio.run_coroutine_threadsafe(coroutine, _LOOP.loop())
    return future.result()


authoring_provider = AuthoringProvider()
