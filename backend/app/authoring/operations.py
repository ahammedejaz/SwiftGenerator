from __future__ import annotations

import hashlib
import hmac
from time import monotonic
from uuid import uuid4

from sqlalchemy import select

from app.authoring.models import (
    ConnectorEnvironment,
    ConnectorSummary,
    ConnectorType,
    DraftStatus,
    ExternalValidationImportRequest,
    SessionUser,
    SubmissionRequest,
    SubmissionResponse,
)
from app.authoring.repository import AuthoringRepository
from app.authoring.service import AuthoringService
from app.config import Settings
from app.persistence.database import SessionLocal
from app.persistence.models import (
    ConnectorRecord,
    ExternalValidationRecord,
    MessageApprovalRecord,
    MessageDraftRecord,
    PlatformAuditRecord,
    SubmissionAttemptRecord,
    SubmissionRecord,
)
from app.specifications.models import CapabilityState


def _idempotency_hash(settings: Settings, tenant_id: str, value: str) -> str:
    if settings.session_hmac_secret is None:
        raise RuntimeError("Submission security is not configured")
    return hmac.new(
        settings.session_hmac_secret.get_secret_value().encode(),
        f"{tenant_id}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _summary(record: ConnectorRecord) -> ConnectorSummary:
    return ConnectorSummary(
        connector_id=record.id,
        name=record.name,
        connector_type=ConnectorType(record.connector_type),
        environment=ConnectorEnvironment(record.environment),
        capability=CapabilityState(record.capability),
        destination_alias=record.destination_alias,
        active=record.active,
    )


class OperationsService:
    def __init__(
        self,
        settings: Settings,
        authoring: AuthoringService,
        repository: AuthoringRepository,
    ) -> None:
        self.settings = settings
        self.authoring = authoring
        self.repository = repository

    def list_connectors(self, user: SessionUser) -> list[ConnectorSummary]:
        with SessionLocal() as session:
            records = list(
                session.scalars(
                    select(ConnectorRecord)
                    .where(ConnectorRecord.tenant_id == user.tenant_id)
                    .order_by(ConnectorRecord.environment, ConnectorRecord.name)
                )
            )
            return [_summary(item) for item in records]

    def connector_health(self, user: SessionUser, connector_id: str) -> dict[str, object]:
        with SessionLocal() as session:
            record = session.get(ConnectorRecord, connector_id)
            if record is None or record.tenant_id != user.tenant_id:
                raise KeyError("connector")
            operational = record.connector_type in {"DOWNLOAD_ONLY", "MOCK_UAT"}
            return {
                "connector": _summary(record).model_dump(mode="json", by_alias=True),
                "configured": record.active,
                "operational": operational,
                "liveProbePerformed": False,
                "message": (
                    "No external probe is performed by the safe health endpoint."
                    if operational
                    else "Connector contract is catalogue-only and is not operational."
                ),
            }

    def test_connector(self, user: SessionUser, connector_id: str) -> dict[str, object]:
        health = self.connector_health(user, connector_id)
        connector = health["connector"]
        assert isinstance(connector, dict)
        connector_type = connector.get("connectorType")
        if connector_type == ConnectorType.MOCK_UAT.value:
            if not self.settings.mock_uat_connector_enabled or self.settings.app_env not in {
                "development",
                "test",
            }:
                raise ValueError("The explicit test connector is disabled")
            return {
                "connectorId": connector_id,
                "outcome": "MOCK_CONNECTOR_SELF_TEST_PASSED",
                "externalNetworkContacted": False,
                "acknowledgementGenerated": False,
            }
        if connector_type == ConnectorType.DOWNLOAD_ONLY.value:
            return {
                "connectorId": connector_id,
                "outcome": "DOWNLOAD_ONLY_READY",
                "externalNetworkContacted": False,
                "acknowledgementGenerated": False,
            }
        raise ValueError("No operational connector adapter is configured")

    def import_external_validation(
        self,
        user: SessionUser,
        draft_id: str,
        payload: ExternalValidationImportRequest,
    ) -> str:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            if draft is None or draft.tenant_id != user.tenant_id:
                raise KeyError("draft")
            if draft.current_checksum != payload.message_checksum:
                raise ValueError("Validation evidence hash does not match the current revision")
            if draft.profile_id != payload.profile_id:
                raise ValueError("Validation evidence profile does not match the draft")
            if draft.standards_release != payload.standards_release:
                raise ValueError("Validation evidence release does not match the draft")
            validation_id = str(uuid4())
            session.add(
                ExternalValidationRecord(
                    id=validation_id,
                    tenant_id=user.tenant_id,
                    draft_id=draft_id,
                    message_checksum=payload.message_checksum,
                    provider_type=payload.provider_type,
                    profile_id=payload.profile_id,
                    standards_release=payload.standards_release,
                    status="PASSED" if payload.passed else "FAILED",
                    safe_findings=payload.safe_findings,
                    validated_at=payload.validated_at,
                    imported_by=user.user_id,
                )
            )
            session.add(
                PlatformAuditRecord(
                    id=str(uuid4()),
                    tenant_id=user.tenant_id,
                    actor_id=user.user_id,
                    action="EXTERNAL_VALIDATION_IMPORTED",
                    resource_type="MESSAGE_DRAFT",
                    resource_id=draft_id,
                    safe_metadata={
                        "status": "PASSED" if payload.passed else "FAILED",
                        "providerType": payload.provider_type,
                        "checksum": payload.message_checksum,
                    },
                )
            )
            session.commit()
            return validation_id

    def external_validations(self, user: SessionUser, draft_id: str) -> list[dict[str, object]]:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            if draft is None or draft.tenant_id != user.tenant_id:
                raise KeyError("draft")
            records = list(
                session.scalars(
                    select(ExternalValidationRecord)
                    .where(
                        ExternalValidationRecord.tenant_id == user.tenant_id,
                        ExternalValidationRecord.draft_id == draft_id,
                    )
                    .order_by(ExternalValidationRecord.created_at.desc())
                )
            )
            return [
                {
                    "validationId": item.id,
                    "messageChecksum": item.message_checksum,
                    "providerType": item.provider_type,
                    "profileId": item.profile_id,
                    "standardsRelease": item.standards_release,
                    "status": item.status,
                    "validatedAt": item.validated_at,
                    "safeFindings": item.safe_findings,
                }
                for item in records
            ]

    def submit(
        self, user: SessionUser, draft_id: str, payload: SubmissionRequest
    ) -> SubmissionResponse:
        composed = self.authoring.compose(user, draft_id)
        self.authoring.ensure_submission_eligible(composed)
        key_hash = _idempotency_hash(self.settings, user.tenant_id, payload.idempotency_key)
        with SessionLocal() as session:
            existing = session.scalar(
                select(SubmissionRecord).where(SubmissionRecord.idempotency_key_hash == key_hash)
            )
            if existing:
                if existing.tenant_id != user.tenant_id or existing.draft_id != draft_id:
                    raise ValueError("The idempotency key is already bound to another request")
                connector = session.get(ConnectorRecord, existing.connector_id)
                assert connector is not None
                return self._submission_response(existing, connector)
            draft = session.get(MessageDraftRecord, draft_id)
            if draft is None or draft.tenant_id != user.tenant_id:
                raise KeyError("draft")
            approval = session.scalar(
                select(MessageApprovalRecord).where(
                    MessageApprovalRecord.draft_id == draft_id,
                    MessageApprovalRecord.revision == draft.revision,
                    MessageApprovalRecord.message_checksum == composed.checksum,
                    MessageApprovalRecord.active,
                )
            )
            if approval is None or draft.status != DraftStatus.APPROVED.value:
                raise ValueError(
                    "An active approval for the current immutable revision is required"
                )
            connector = session.get(ConnectorRecord, payload.connector_id)
            if connector is None or connector.tenant_id != user.tenant_id or not connector.active:
                raise ValueError("The connector is not available to this tenant")
            if connector.connector_type == ConnectorType.DOWNLOAD_ONLY.value:
                raise ValueError("Download-only connectors cannot submit messages")
            if connector.environment == ConnectorEnvironment.PRODUCTION.value:
                if (
                    self.settings.submission_mode != "production"
                    or not self.settings.production_submission_enabled
                    or not payload.confirm_production
                ):
                    raise ValueError("Production submission is disabled or not confirmed")
            elif connector.environment == ConnectorEnvironment.UAT.value:
                if self.settings.submission_mode not in {"uat", "production"}:
                    raise ValueError("UAT submission is disabled")
            if self.settings.external_validation_required_for_submission:
                evidence = session.scalar(
                    select(ExternalValidationRecord.id).where(
                        ExternalValidationRecord.tenant_id == user.tenant_id,
                        ExternalValidationRecord.draft_id == draft_id,
                        ExternalValidationRecord.message_checksum == composed.checksum,
                        ExternalValidationRecord.status == "PASSED",
                    )
                )
                if evidence is None:
                    raise ValueError("Passing external validation evidence is required")
            if connector.connector_type != ConnectorType.MOCK_UAT.value:
                raise ValueError(
                    "This connector contract is not operational in the current deployment"
                )
            if not self.settings.mock_uat_connector_enabled or self.settings.app_env not in {
                "development",
                "test",
            }:
                raise ValueError("The mock UAT connector is disabled")
            started = monotonic()
            submission_id = str(uuid4())
            provider_id = f"MOCK-{uuid4()}"
            acknowledgement = f"MOCK-ACK-{uuid4()}"
            submission = SubmissionRecord(
                id=submission_id,
                tenant_id=user.tenant_id,
                draft_id=draft_id,
                revision=draft.revision,
                connector_id=connector.id,
                idempotency_key_hash=key_hash,
                message_checksum=composed.checksum,
                status=DraftStatus.ACKNOWLEDGED.value,
                submitted_by=user.user_id,
                provider_message_id=provider_id,
                client_correlation_id=submission_id,
                safe_response_code="MOCK_UAT_ACCEPTED",
                acknowledgement_reference=acknowledgement,
                attempt_count=1,
            )
            session.add(submission)
            session.add(
                SubmissionAttemptRecord(
                    id=str(uuid4()),
                    submission_id=submission_id,
                    attempt_number=1,
                    outcome_code="MOCK_UAT_ACCEPTED",
                    retryable=False,
                    latency_ms=int((monotonic() - started) * 1_000),
                )
            )
            draft.status = DraftStatus.ACKNOWLEDGED.value
            session.add(
                PlatformAuditRecord(
                    id=str(uuid4()),
                    tenant_id=user.tenant_id,
                    actor_id=user.user_id,
                    action="MESSAGE_SUBMITTED",
                    resource_type="MESSAGE_DRAFT",
                    resource_id=draft_id,
                    safe_metadata={
                        "connectorId": connector.id,
                        "environment": connector.environment,
                        "checksum": composed.checksum,
                        "outcome": "MOCK_UAT_ACCEPTED",
                    },
                )
            )
            session.commit()
            session.refresh(submission)
            return self._submission_response(submission, connector)

    def submissions(self, user: SessionUser, draft_id: str) -> list[SubmissionResponse]:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            if draft is None or draft.tenant_id != user.tenant_id:
                raise KeyError("draft")
            records = list(
                session.scalars(
                    select(SubmissionRecord)
                    .where(
                        SubmissionRecord.tenant_id == user.tenant_id,
                        SubmissionRecord.draft_id == draft_id,
                    )
                    .order_by(SubmissionRecord.created_at)
                )
            )
            responses: list[SubmissionResponse] = []
            for item in records:
                connector = session.get(ConnectorRecord, item.connector_id)
                if connector is not None:
                    responses.append(self._submission_response(item, connector))
            return responses

    @staticmethod
    def _submission_response(
        submission: SubmissionRecord, connector: ConnectorRecord
    ) -> SubmissionResponse:
        return SubmissionResponse(
            submission_id=submission.id,
            draft_id=submission.draft_id,
            revision=submission.revision,
            status=DraftStatus(submission.status),
            connector=_summary(connector),
            checksum=submission.message_checksum,
            attempt_count=submission.attempt_count,
            provider_message_id=submission.provider_message_id,
            client_correlation_id=submission.client_correlation_id,
            safe_response_code=submission.safe_response_code,
            acknowledgement_reference=submission.acknowledgement_reference,
        )
