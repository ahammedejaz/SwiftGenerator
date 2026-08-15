from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class AiAuditEvent:
    request_id: str
    scenario_id: str | None
    provider: str
    primary_model: str
    final_model: str | None
    escalated: bool
    escalation_reason: str | None
    prompt_version: str
    schema_version: str
    attempt_count: int
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reported_cost: Decimal | None
    outcome_code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AiAuditSink(Protocol):
    def save(self, event: AiAuditEvent) -> None: ...


class AiAuditWriteError(RuntimeError):
    """Safe signal that content-free audit metadata could not be persisted."""
