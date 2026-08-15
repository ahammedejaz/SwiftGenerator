from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.agents.usage import AiInteractionEvent, AiInteractionWriteError
from app.domain.enums import AiProcessingSource
from app.domain.models import AiUsageInteractionResponse
from app.persistence.database import SessionLocal
from app.persistence.models import AiInteractionRecord


class AiUsageRepository:
    def save_interaction(self, event: AiInteractionEvent) -> None:
        try:
            with SessionLocal.begin() as session:
                session.add(
                    AiInteractionRecord(
                        id=str(uuid4()),
                        interaction_id=event.interaction_id,
                        operation_type=event.operation_type,
                        source=event.source.value,
                        provider=event.provider,
                        model=event.model,
                        escalated=event.escalated,
                        cache_hit=event.cache_hit,
                        cache_namespace=event.cache_namespace,
                        cache_entry_age_seconds=event.cache_entry_age_seconds,
                        live_api_call_count=event.live_api_call_count,
                        primary_call_count=event.primary_call_count,
                        escalation_call_count=event.escalation_call_count,
                        prompt_tokens=event.prompt_tokens,
                        completion_tokens=event.completion_tokens,
                        total_tokens=event.total_tokens,
                        reported_cost=(
                            str(event.reported_cost) if event.reported_cost is not None else None
                        ),
                        latency_ms=event.latency_ms,
                        tokens_avoided=event.tokens_avoided,
                        calls_avoided=event.calls_avoided,
                        cost_avoided=(
                            str(event.cost_avoided) if event.cost_avoided is not None else None
                        ),
                        prompt_version=event.prompt_version,
                        schema_version=event.schema_version,
                        knowledge_version=event.knowledge_version,
                        profile_version=event.profile_version,
                        outcome_code=event.outcome_code,
                        created_at=event.created_at,
                    )
                )
        except SQLAlchemyError as exc:
            raise AiInteractionWriteError("AI interaction metadata persistence failed") from exc

    def last_interaction(self) -> AiInteractionRecord | None:
        with SessionLocal() as session:
            return session.scalar(
                select(AiInteractionRecord).order_by(desc(AiInteractionRecord.created_at)).limit(1)
            )

    def last_provider_call(self) -> AiInteractionRecord | None:
        with SessionLocal() as session:
            return session.scalar(
                select(AiInteractionRecord)
                .where(AiInteractionRecord.live_api_call_count > 0)
                .order_by(desc(AiInteractionRecord.created_at))
                .limit(1)
            )

    def summary(self, days: int) -> dict[str, int | str]:
        since = datetime.now(UTC) - timedelta(days=days)
        with SessionLocal() as session:
            row = session.execute(
                select(
                    func.count(AiInteractionRecord.id),
                    func.coalesce(func.sum(AiInteractionRecord.live_api_call_count), 0),
                    func.coalesce(func.sum(AiInteractionRecord.total_tokens), 0),
                    func.coalesce(func.sum(AiInteractionRecord.tokens_avoided), 0),
                    func.coalesce(func.sum(AiInteractionRecord.calls_avoided), 0),
                    func.coalesce(func.avg(AiInteractionRecord.latency_ms), 0),
                    func.coalesce(
                        func.sum(case((AiInteractionRecord.cache_hit.is_(True), 1), else_=0)),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (AiInteractionRecord.source == "DETERMINISTIC", 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(AiInteractionRecord.created_at >= since)
            ).one()
            costs = session.execute(
                select(
                    AiInteractionRecord.reported_cost,
                    AiInteractionRecord.cost_avoided,
                ).where(AiInteractionRecord.created_at >= since)
            ).all()
        total_cost = sum((Decimal(item[0]) for item in costs if item[0] is not None), Decimal("0"))
        avoided_cost = sum(
            (Decimal(item[1]) for item in costs if item[1] is not None), Decimal("0")
        )
        return {
            "interactions": int(row[0]),
            "liveApiCalls": int(row[1]),
            "tokensConsumed": int(row[2]),
            "tokensAvoided": int(row[3]),
            "apiCallsAvoided": int(row[4]),
            "averageLatencyMs": round(float(row[5])),
            "cacheHits": int(row[6]),
            "deterministicInteractions": int(row[7]),
            "providerReportedCost": str(total_cost),
            "estimatedCostAvoided": str(avoided_cost),
        }


ai_usage_repository = AiUsageRepository()


def interaction_response(record: AiInteractionRecord) -> AiUsageInteractionResponse:
    return AiUsageInteractionResponse(
        interaction_id=record.interaction_id,
        operation_type=record.operation_type,
        source=AiProcessingSource(record.source),
        provider=record.provider,
        model=record.model,
        escalated=record.escalated,
        cache_hit=record.cache_hit,
        cache_namespace=record.cache_namespace,
        cache_entry_age_seconds=record.cache_entry_age_seconds,
        live_api_call_count=record.live_api_call_count,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        provider_reported_cost=(
            Decimal(record.reported_cost) if record.reported_cost is not None else None
        ),
        latency_ms=record.latency_ms,
        tokens_avoided=record.tokens_avoided,
        calls_avoided=record.calls_avoided,
        estimated_cost_avoided=(
            Decimal(record.cost_avoided) if record.cost_avoided is not None else None
        ),
        prompt_version=record.prompt_version,
        schema_version=record.schema_version,
        knowledge_version=record.knowledge_version,
        profile_version=record.profile_version,
        outcome_code=record.outcome_code,
        created_at=record.created_at,
    )
