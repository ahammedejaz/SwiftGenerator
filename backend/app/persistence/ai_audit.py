from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.agents.audit import AiAuditEvent, AiAuditWriteError
from app.persistence.database import SessionLocal
from app.persistence.models import AiAuditRecord


class AiAuditRepository:
    """Persists content-free operational metadata; prompts and outputs are never accepted."""

    def save(self, event: AiAuditEvent) -> None:
        record = AiAuditRecord(
            id=str(uuid4()),
            request_id=event.request_id,
            scenario_id=event.scenario_id,
            provider=event.provider,
            primary_model=event.primary_model,
            final_model=event.final_model,
            escalated=event.escalated,
            escalation_reason=event.escalation_reason,
            prompt_version=event.prompt_version,
            schema_version=event.schema_version,
            attempt_count=event.attempt_count,
            latency_ms=event.latency_ms,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            total_tokens=event.total_tokens,
            reported_cost=(str(event.reported_cost) if event.reported_cost is not None else None),
            outcome_code=event.outcome_code,
            created_at=event.created_at,
        )
        try:
            with SessionLocal.begin() as session:
                session.add(record)
        except SQLAlchemyError as exc:
            raise AiAuditWriteError("AI audit metadata persistence failed") from exc


ai_audit_repository = AiAuditRepository()
