"""Choosing a structured-completion client, and the scripted one CI uses.

Normal tests and normal CI must never reach a network. They use
:class:`ScriptedCompletionClient`, which answers from a table keyed by role and segment —
so a test can stage a correct pass, a wrong-field pass, an over-broad reading, a
hallucinated code, an instruction-following failure or a no-rule answer, and assert what
the deterministic half does with each.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.errors import ai_error
from app.agents.providers.base import (
    ModelUsage,
    StructuredCompletionClient,
    StructuredCompletionRequest,
    StructuredCompletionResponse,
)
from app.config import Settings, get_settings


@dataclass
class ScriptedCompletionClient:
    """A deterministic stand-in for a provider. No network, ever."""

    #: (role, segment_id) -> the payload the model would have returned.
    answers: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    #: Fallback when no exact answer is staged.
    default: Callable[[StructuredCompletionRequest], dict[str, Any]] | None = None
    calls: list[StructuredCompletionRequest] = field(default_factory=list)
    provider_name: str = "scripted"

    async def complete(
        self, request: StructuredCompletionRequest
    ) -> StructuredCompletionResponse:
        self.calls.append(request)
        segment_id = _segment_id_of(request.user_content)
        payload = self.answers.get((request.role, segment_id))
        if payload is None and self.default is not None:
            payload = self.default(request)
        if payload is None:
            raise ai_error("AI_NOT_CONFIGURED")
        return StructuredCompletionResponse(
            payload=payload,
            model=request.model,
            attempt_count=1,
            latency_ms=0,
            usage=ModelUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            provider=self.provider_name,
        )

    async def aclose(self) -> None:
        return None


def _segment_id_of(user_content: str) -> str:
    for line in user_content.splitlines():
        if line.startswith("SEGMENT_ID: "):
            return line.removeprefix("SEGMENT_ID: ").strip()
    return ""


@dataclass(frozen=True)
class ExtractionModels:
    extractor_a: str
    extractor_b: str
    refuter: str

    def all(self) -> tuple[str, str, str]:
        return self.extractor_a, self.extractor_b, self.refuter


def configured_models(settings: Settings | None = None) -> ExtractionModels:
    """Which models the three roles use.

    Defaulting to the already-pinned interpretation models keeps one approved list rather
    than a second one to review. Distinct providers are supported but never required: the
    passes are isolated by *call*, and calling them independent authorities would be
    dishonest whether or not the vendors differ.
    """
    resolved = settings or get_settings()
    primary = resolved.openrouter_primary_model
    escalation = resolved.openrouter_escalation_model
    return ExtractionModels(
        extractor_a=resolved.rule_extractor_model or primary,
        extractor_b=resolved.rule_secondary_extractor_model or escalation,
        refuter=resolved.rule_refuter_model or escalation,
    )


def live_client(settings: Settings | None = None) -> StructuredCompletionClient | None:
    """The configured provider, or ``None`` when no credential is available.

    ``None`` is reported honestly as LIVE_EXTRACTION_NOT_VERIFIED. It is never replaced by
    a scripted client pretending to be live.
    """
    resolved = settings or get_settings()
    if resolved.ai_provider != "openrouter":
        return None
    from app.agents.providers.openrouter import OpenRouterClient

    client = OpenRouterClient(resolved)
    if not client.configured:
        return None
    return client
