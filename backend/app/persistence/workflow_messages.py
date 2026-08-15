from __future__ import annotations

from sqlalchemy import select

from app.domain.enums import MessageType
from app.domain.models import RenderedField, ValidationReport
from app.knowledge.models import WorkflowModuleId
from app.persistence.database import SessionLocal
from app.persistence.models import WorkflowMessageRecord
from app.workflows.models import (
    WorkflowGeneratedMessage,
    WorkflowLifecycle,
    WorkflowLifecycleEntry,
)


class WorkflowMessageRepository:
    def save(self, message: WorkflowGeneratedMessage) -> None:
        with SessionLocal.begin() as session:
            session.add(
                WorkflowMessageRecord(
                    id=message.message_id,
                    workflow_id=message.workflow_id,
                    workflow_module=message.workflow_module.value,
                    message_type=message.resolved_message_type.value,
                    canonical_data=message.canonical_data,
                    raw_message=message.raw_message,
                    field_map=[
                        item.model_dump(mode="json", by_alias=True) for item in message.field_map
                    ],
                    profile_id=message.profile_id,
                    profile_version=message.profile_version,
                    validation_payload=message.validation.model_dump(mode="json", by_alias=True),
                    related_workflow_message_id=message.related_workflow_message_id,
                    related_settlement_message_id=message.related_settlement_message_id,
                    disclaimer=message.disclaimer,
                    created_at=message.created_at,
                )
            )

    def get(self, message_id: str) -> WorkflowGeneratedMessage:
        with SessionLocal() as session:
            record = session.get(WorkflowMessageRecord, message_id)
            if record is None:
                raise KeyError(f"Unknown workflow message: {message_id}")
            return self._to_model(record)

    def reference_exists(self, reference: str) -> bool:
        with SessionLocal() as session:
            records = session.scalars(select(WorkflowMessageRecord.canonical_data)).all()
            return any(
                payload.get("statementReference") == reference
                or payload.get("eventReference") == reference
                or payload.get("instructionReference") == reference
                for payload in records
            )

    def lifecycle(self, workflow_id: str) -> WorkflowLifecycle:
        with SessionLocal() as session:
            records = list(
                session.scalars(
                    select(WorkflowMessageRecord)
                    .where(WorkflowMessageRecord.workflow_id == workflow_id)
                    .order_by(WorkflowMessageRecord.created_at)
                ).all()
            )
        if not records:
            raise KeyError(f"Unknown workflow: {workflow_id}")
        entries = [
            WorkflowLifecycleEntry(
                message_id=item.id,
                message_type=MessageType(item.message_type),
                workflow_module=WorkflowModuleId(item.workflow_module),
                business_status=self._business_status(item),
                related_workflow_message_id=item.related_workflow_message_id,
                related_settlement_message_id=item.related_settlement_message_id,
                validation_status=item.validation_payload["status"],
                created_at=item.created_at,
            )
            for item in records
        ]
        return WorkflowLifecycle(
            workflow_id=workflow_id,
            entries=entries,
            correlation_valid=all(item.validation_status == "VALID" for item in entries),
        )

    @staticmethod
    def _business_status(record: WorkflowMessageRecord) -> str:
        data = record.canonical_data
        if record.message_type == MessageType.MT537.value:
            return f"Penalty statement ({len(data.get('penalties', []))} penalties)"
        value = data.get("businessStatus", record.message_type)
        return str(value)

    @staticmethod
    def _to_model(record: WorkflowMessageRecord) -> WorkflowGeneratedMessage:
        return WorkflowGeneratedMessage(
            message_id=record.id,
            workflow_id=record.workflow_id,
            workflow_module=WorkflowModuleId(record.workflow_module),
            resolved_message_type=MessageType(record.message_type),
            canonical_data=record.canonical_data,
            raw_message=record.raw_message,
            field_map=[RenderedField.model_validate(item) for item in record.field_map],
            profile_id=record.profile_id,
            profile_version=record.profile_version,
            validation=ValidationReport.model_validate(record.validation_payload),
            related_workflow_message_id=record.related_workflow_message_id,
            related_settlement_message_id=record.related_settlement_message_id,
            disclaimer=record.disclaimer,
            created_at=record.created_at,
        )


workflow_message_repository = WorkflowMessageRepository()
