from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.agents.cache import AiCacheEntry, AiCacheNamespace, AiCachePersistenceError
from app.agents.providers.base import ModelUsage
from app.persistence.database import SessionLocal
from app.persistence.models import AiCacheRecord


class SqlAlchemyAiCacheRepository:
    """Stores schema-validated placeholder templates, never raw prompts or secret mappings."""

    def get(self, cache_id: str) -> AiCacheEntry | None:
        try:
            with SessionLocal() as session:
                record = session.get(AiCacheRecord, cache_id)
                return _to_entry(record) if record is not None else None
        except SQLAlchemyError as exc:
            raise AiCachePersistenceError("AI cache lookup failed") from exc

    def save(self, entry: AiCacheEntry) -> None:
        record = AiCacheRecord(
            id=entry.cache_id,
            namespace=entry.namespace.value,
            key_version=entry.key_version,
            prompt_version=entry.prompt_version,
            schema_version=entry.schema_version,
            knowledge_version=entry.knowledge_version,
            taxonomy_version=entry.taxonomy_version,
            model=entry.model,
            workflow_module=entry.workflow_module,
            profile_id=entry.profile_id,
            profile_version=entry.profile_version,
            standards_release=entry.standards_release,
            result_payload=entry.result_payload,
            prompt_tokens=entry.usage.prompt_tokens,
            completion_tokens=entry.usage.completion_tokens,
            total_tokens=entry.usage.total_tokens,
            reported_cost=(
                str(entry.usage.reported_cost) if entry.usage.reported_cost is not None else None
            ),
            escalated=entry.escalated,
            escalation_reason=entry.escalation_reason,
            attempt_count=entry.attempt_count,
            schema_retries=entry.schema_retries,
            created_at=entry.created_at,
            expires_at=entry.expires_at,
            last_accessed_at=entry.last_accessed_at,
            hit_count=entry.hit_count,
        )
        try:
            with SessionLocal.begin() as session:
                session.merge(record)
        except SQLAlchemyError as exc:
            raise AiCachePersistenceError("AI cache write failed") from exc

    def touch(self, cache_id: str, accessed_at: datetime) -> None:
        with SessionLocal.begin() as session:
            session.execute(
                update(AiCacheRecord)
                .where(AiCacheRecord.id == cache_id)
                .values(
                    last_accessed_at=accessed_at,
                    hit_count=AiCacheRecord.hit_count + 1,
                )
            )

    def delete(self, cache_id: str) -> None:
        with SessionLocal.begin() as session:
            session.execute(delete(AiCacheRecord).where(AiCacheRecord.id == cache_id))

    def stats(self) -> dict[str, int]:
        with SessionLocal() as session:
            entries, hits = session.execute(
                select(
                    func.count(AiCacheRecord.id),
                    func.coalesce(func.sum(AiCacheRecord.hit_count), 0),
                )
            ).one()
            return {
                "entries": int(entries),
                "activeEntries": int(
                    session.scalar(
                        select(func.count(AiCacheRecord.id)).where(
                            AiCacheRecord.expires_at > datetime.now().astimezone()
                        )
                    )
                    or 0
                ),
                "totalHits": int(hits),
            }


def _to_entry(record: AiCacheRecord) -> AiCacheEntry:
    return AiCacheEntry(
        cache_id=record.id,
        namespace=AiCacheNamespace(record.namespace),
        key_version=record.key_version,
        prompt_version=record.prompt_version,
        schema_version=record.schema_version,
        knowledge_version=record.knowledge_version,
        taxonomy_version=record.taxonomy_version,
        model=record.model,
        workflow_module=record.workflow_module,
        profile_id=record.profile_id,
        profile_version=record.profile_version,
        standards_release=record.standards_release,
        result_payload=record.result_payload,
        usage=ModelUsage(
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            total_tokens=record.total_tokens,
            reported_cost=(
                Decimal(record.reported_cost) if record.reported_cost is not None else None
            ),
        ),
        escalated=record.escalated,
        escalation_reason=record.escalation_reason,
        attempt_count=record.attempt_count,
        schema_retries=record.schema_retries,
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_accessed_at=record.last_accessed_at,
        hit_count=record.hit_count,
    )


ai_cache_repository = SqlAlchemyAiCacheRepository()
