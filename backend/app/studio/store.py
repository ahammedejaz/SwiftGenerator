"""Persistence for generated studio messages.

Deliberately small: one additive table so testers can find what they generated a few
minutes ago without an account, and so a message id can be turned back into a download.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.persistence.database import SessionLocal
from app.persistence.models import StudioMessageRecord
from app.studio.models import GenerateResult, MessageFormat, MessageOutputs, RecentMessage

#: How many messages the recent list keeps. Old rows are trimmed on write.
RETENTION_LIMIT = 500
RETENTION_DAYS = 30


class StudioMessageStore:
    def save(
        self,
        result: GenerateResult,
        *,
        inputs: dict[str, object],
        source: str = "API",
    ) -> str:
        message_id = result.message_id or str(uuid4())
        with SessionLocal() as session:
            session.add(
                StudioMessageRecord(
                    id=message_id,
                    correlation_id=result.correlation_id,
                    scenario_id=result.scenario_id,
                    format=result.format.value,
                    message_type=result.message_type,
                    version=result.version,
                    profile_id=result.profile_id,
                    profile_version=result.profile_version,
                    valid=result.valid,
                    error_count=len(result.validation.errors),
                    warning_count=len(result.validation.warnings),
                    checksum=result.checksum,
                    source=source,
                    outputs_json=result.outputs.model_dump_json(by_alias=True),
                    inputs_json=json.dumps(inputs, default=str),
                    validation_json=result.validation.model_dump_json(by_alias=True),
                )
            )
            self._trim(session)
            session.commit()
        return message_id

    @staticmethod
    def _trim(session) -> None:  # type: ignore[no-untyped-def]
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        session.execute(
            delete(StudioMessageRecord).where(StudioMessageRecord.created_at < cutoff)
        )
        total = session.scalar(select(func.count()).select_from(StudioMessageRecord)) or 0
        if total > RETENTION_LIMIT:
            surplus = total - RETENTION_LIMIT
            stale = session.scalars(
                select(StudioMessageRecord.id)
                .order_by(StudioMessageRecord.created_at.asc())
                .limit(surplus)
            ).all()
            if stale:
                session.execute(
                    delete(StudioMessageRecord).where(StudioMessageRecord.id.in_(stale))
                )

    def recent(self, limit: int = 50, format_: MessageFormat | None = None) -> list[RecentMessage]:
        with SessionLocal() as session:
            statement = select(StudioMessageRecord).order_by(
                StudioMessageRecord.created_at.desc()
            )
            if format_ is not None:
                statement = statement.where(StudioMessageRecord.format == format_.value)
            records = session.scalars(statement.limit(limit)).all()
            return [_summary(record) for record in records]

    def get(self, message_id: str) -> tuple[RecentMessage, MessageOutputs]:
        with SessionLocal() as session:
            record = session.get(StudioMessageRecord, message_id)
            if record is None:
                raise KeyError(f"Unknown message: {message_id}")
            return _summary(record), MessageOutputs.model_validate_json(record.outputs_json)

    def inputs(self, message_id: str) -> dict[str, object]:
        with SessionLocal() as session:
            record = session.get(StudioMessageRecord, message_id)
            if record is None:
                raise KeyError(f"Unknown message: {message_id}")
            payload = json.loads(record.inputs_json)
            return payload if isinstance(payload, dict) else {}

    def clear(self) -> int:
        with SessionLocal() as session:
            total = session.scalar(select(func.count()).select_from(StudioMessageRecord)) or 0
            session.execute(delete(StudioMessageRecord))
            session.commit()
            return int(total)


def _summary(record: StudioMessageRecord) -> RecentMessage:
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return RecentMessage(
        message_id=record.id,
        correlation_id=record.correlation_id,
        scenario_id=record.scenario_id,
        format=MessageFormat(record.format),
        message_type=record.message_type,
        profile_id=record.profile_id,
        valid=record.valid,
        error_count=record.error_count,
        warning_count=record.warning_count,
        checksum=record.checksum,
        source=record.source,
        created_at=created,
    )


studio_message_store = StudioMessageStore()
