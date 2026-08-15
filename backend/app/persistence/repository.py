from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.domain.enums import (
    Lifecycle,
    MessageFunction,
    MessageType,
    Severity,
    StatusCategory,
    ValidationStatus,
)
from app.domain.models import (
    GeneratedMessage,
    LifecycleEntry,
    LifecycleTimeline,
    RenderedField,
    SettlementScenario,
    ValidationFinding,
    ValidationReport,
)
from app.persistence.database import SessionLocal
from app.persistence.models import (
    MessageRecord,
    ReportRecord,
    ScenarioRecord,
    ValidationResultRecord,
)


class MessageRepository:
    def save(self, generated: GeneratedMessage, related_message_id: str | None = None) -> None:
        scenario_db_id = str(uuid4())
        scenario = generated.scenario
        scenario_record = ScenarioRecord(
            id=scenario_db_id,
            scenario_id=scenario.scenario_id,
            profile_id=generated.profile_id,
            profile_version=generated.profile_version,
            canonical_data=scenario.model_dump(mode="json", by_alias=True),
            lifecycle=scenario.lifecycle.value,
            direction=scenario.direction.value if scenario.direction else None,
            payment_type=scenario.payment_type.value if scenario.payment_type else None,
            message_type=generated.resolved_message_type.value,
            generation_mode=scenario.test_configuration.mode.value,
            synthetic_data=scenario.synthetic_data,
        )
        message_record = MessageRecord(
            id=generated.message_id,
            scenario_id=scenario_db_id,
            message_type=generated.resolved_message_type.value,
            raw_message=generated.raw_message,
            field_map=[item.model_dump(mode="json", by_alias=True) for item in generated.field_map],
            related_message_id=related_message_id,
            sender_reference=scenario.sender_reference or "",
            validation_status=generated.validation.status.value,
            profile_id=generated.profile_id,
            profile_version=generated.profile_version,
            disclaimer=generated.disclaimer,
            created_at=generated.created_at,
        )
        findings = [
            ValidationResultRecord(
                id=str(uuid4()),
                message_id=generated.message_id,
                rule_id=item.rule_id,
                severity=item.severity.value,
                field_path=item.field_path,
                message_text=item.message,
                technical_explanation=item.technical_explanation,
                current_value=item.current_value,
                expected_condition=item.expected_condition,
                suggestion=item.suggestion,
                intentional=item.intentional,
            )
            for item in generated.validation.findings
        ]
        with SessionLocal.begin() as session:
            session.add(scenario_record)
            session.add(message_record)
            session.add_all(findings)

    def get(self, message_id: str) -> GeneratedMessage:
        with SessionLocal() as session:
            record = session.scalar(
                select(MessageRecord)
                .options(selectinload(MessageRecord.scenario), selectinload(MessageRecord.findings))
                .where(MessageRecord.id == message_id)
            )
            if record is None:
                raise KeyError(f"Unknown message: {message_id}")
            return self._to_generated(record)

    def get_related_message_id(self, message_id: str) -> str | None:
        with SessionLocal() as session:
            record = session.get(MessageRecord, message_id)
            if record is None:
                raise KeyError(f"Unknown message: {message_id}")
            return record.related_message_id

    def sender_reference_exists(self, sender_reference: str) -> bool:
        with SessionLocal() as session:
            return (
                session.scalar(
                    select(MessageRecord.id)
                    .where(MessageRecord.sender_reference == sender_reference)
                    .limit(1)
                )
                is not None
            )

    def has_active_cancellation(self, original_message_id: str) -> bool:
        with SessionLocal() as session:
            records = list(
                session.scalars(
                    select(MessageRecord).options(selectinload(MessageRecord.scenario))
                ).all()
            )
        children = [
            record for record in records if record.related_message_id == original_message_id
        ]
        cancellation_ids = {
            record.id
            for record in children
            if SettlementScenario.model_validate(record.scenario.canonical_data).function
            == MessageFunction.CANC
        }
        for cancellation_id in cancellation_ids:
            outcomes = [
                SettlementScenario.model_validate(record.scenario.canonical_data)
                for record in records
                if record.related_message_id == cancellation_id
            ]
            if not any(
                outcome.status.category
                in {
                    StatusCategory.CANCELLATION_ACCEPTED,
                    StatusCategory.CANCELLATION_REJECTED,
                }
                for outcome in outcomes
            ):
                return True
        return False

    def lifecycle(self, message_id: str) -> LifecycleTimeline:
        with SessionLocal() as session:
            selected = session.get(MessageRecord, message_id)
            if selected is None:
                raise KeyError(f"Unknown message: {message_id}")
            all_records = list(
                session.scalars(
                    select(MessageRecord)
                    .options(
                        selectinload(MessageRecord.scenario), selectinload(MessageRecord.findings)
                    )
                    .order_by(MessageRecord.created_at)
                ).all()
            )
            by_id = {record.id: record for record in all_records}
            root_id = selected.id
            seen_ancestors: set[str] = set()
            while root_id not in seen_ancestors:
                seen_ancestors.add(root_id)
                parent_id = by_id[root_id].related_message_id
                if parent_id is None or parent_id not in by_id:
                    break
                root_id = parent_id
            included = {root_id}
            changed = True
            while changed:
                changed = False
                for record in all_records:
                    if record.related_message_id in included and record.id not in included:
                        included.add(record.id)
                        changed = True
            records = [record for record in all_records if record.id in included]
            entries = [self._to_lifecycle_entry(record) for record in records]
            correlation_findings = [
                finding
                for record in records
                for finding in self._finding_models(record)
                if finding.rule_id.startswith("LIFECYCLE-")
                or finding.rule_id.startswith("CONFIRMATION-")
                or finding.rule_id.startswith("CANCELLATION-")
            ]
            return LifecycleTimeline(
                root_message_id=root_id,
                entries=entries,
                correlation_valid=not any(
                    finding.severity == Severity.ERROR for finding in correlation_findings
                ),
                correlation_findings=correlation_findings,
            )

    def reset_synthetic(self) -> int:
        with SessionLocal.begin() as session:
            message_count = len(
                session.scalars(
                    select(MessageRecord.id)
                    .join(ScenarioRecord)
                    .where(ScenarioRecord.synthetic_data.is_(True))
                ).all()
            )
            session.execute(delete(ReportRecord))
            synthetic_scenarios = select(ScenarioRecord.id).where(
                ScenarioRecord.synthetic_data.is_(True)
            )
            synthetic_messages = select(MessageRecord.id).where(
                MessageRecord.scenario_id.in_(synthetic_scenarios)
            )
            session.execute(
                delete(ValidationResultRecord).where(
                    ValidationResultRecord.message_id.in_(synthetic_messages)
                )
            )
            session.execute(
                delete(MessageRecord).where(MessageRecord.scenario_id.in_(synthetic_scenarios))
            )
            session.execute(delete(ScenarioRecord).where(ScenarioRecord.synthetic_data.is_(True)))
            return message_count

    def _to_generated(self, record: MessageRecord) -> GeneratedMessage:
        findings = self._finding_models(record)
        error_count = sum(item.severity == Severity.ERROR for item in findings)
        warning_count = sum(item.severity == Severity.WARNING for item in findings)
        return GeneratedMessage(
            message_id=record.id,
            scenario=SettlementScenario.model_validate(record.scenario.canonical_data),
            resolved_message_type=MessageType(record.message_type),
            raw_message=record.raw_message,
            field_map=[RenderedField.model_validate(item) for item in record.field_map],
            profile_id=record.profile_id,
            profile_version=record.profile_version,
            validation=ValidationReport(
                status=ValidationStatus(record.validation_status),
                profile_id=record.profile_id,
                profile_version=record.profile_version,
                findings=findings,
                error_count=error_count,
                warning_count=warning_count,
            ),
            disclaimer=record.disclaimer,
            intentional_invalid_notice=(
                "Intentionally invalid message generated for negative testing."
                if record.validation_status == ValidationStatus.INTENTIONALLY_INVALID.value
                else None
            ),
            created_at=record.created_at,
        )

    def _finding_models(self, record: MessageRecord) -> list[ValidationFinding]:
        return [
            ValidationFinding(
                rule_id=item.rule_id,
                severity=Severity(item.severity),
                field_path=item.field_path,
                message=item.message_text,
                technical_explanation=item.technical_explanation,
                current_value=item.current_value,
                expected_condition=item.expected_condition,
                suggestion=item.suggestion,
                intentional=item.intentional,
            )
            for item in record.findings
        ]

    def _to_lifecycle_entry(self, record: MessageRecord) -> LifecycleEntry:
        scenario = SettlementScenario.model_validate(record.scenario.canonical_data)
        business_status = "Instruction"
        if scenario.message_type == MessageType.MT530:
            business_status = "Processing command"
        elif scenario.function == MessageFunction.CANC:
            business_status = "Cancellation request"
        elif scenario.lifecycle == Lifecycle.STATUS:
            business_status = (
                scenario.status.category.value if scenario.status.category else "Status"
            )
        elif scenario.lifecycle == Lifecycle.CONFIRMATION:
            business_status = (
                scenario.confirmation.settlement_result.value
                if scenario.confirmation.settlement_result
                else "Confirmation"
            )
        return LifecycleEntry(
            message_id=record.id,
            message_type=MessageType(record.message_type),
            related_message_id=record.related_message_id,
            sender_reference=record.sender_reference,
            related_reference=scenario.related_reference,
            lifecycle=scenario.lifecycle,
            business_status=business_status,
            profile_id=record.profile_id,
            profile_version=record.profile_version,
            validation_status=ValidationStatus(record.validation_status),
            created_at=record.created_at,
        )


message_repository = MessageRepository()
