from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from app.domain.enums import AiProcessingSource


@dataclass(frozen=True)
class AiInteractionEvent:
    interaction_id: str
    operation_type: str
    source: AiProcessingSource
    provider: str | None
    model: str | None
    escalated: bool
    cache_hit: bool
    cache_namespace: str | None
    cache_entry_age_seconds: int | None
    live_api_call_count: int
    primary_call_count: int
    escalation_call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reported_cost: Decimal | None
    latency_ms: int
    tokens_avoided: int
    calls_avoided: int
    cost_avoided: Decimal | None
    prompt_version: str
    schema_version: str
    knowledge_version: str
    profile_version: str | None
    outcome_code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AiInteractionSink(Protocol):
    def save_interaction(self, event: AiInteractionEvent) -> None: ...


class AiInteractionWriteError(RuntimeError):
    """Safe signal that content-free interaction metadata could not be persisted."""
