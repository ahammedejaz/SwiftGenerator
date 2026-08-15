from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.authoring.composer import ComposeField, ComposeSequence
from app.authoring.models import (
    AuditEventResponse,
    DataClassification,
    DraftField,
    DraftResponse,
    DraftSequence,
    DraftStatus,
    FieldUpsertRequest,
    FieldValueSource,
    PlatformRole,
    SessionUser,
    ValidationLevel,
    ValidationLevelState,
)
from app.config import Settings
from app.domain.enums import MessageType
from app.persistence.database import SessionLocal
from app.persistence.models import (
    DraftFieldRecord,
    DraftSequenceRecord,
    DraftVersionRecord,
    MessageApprovalRecord,
    MessageDraftRecord,
    MessageReviewRecord,
    PlatformAuditRecord,
)
from app.profiles.loader import ProfileRepository
from app.security.classification import classify_field, mask_value
from app.security.encryption import EnvelopeEncryptor
from app.specifications.models import MessageSpecification
from app.specifications.registry import MessageSpecificationRegistry


def _field_aad(tenant_id: str, draft_id: str, field_id: str) -> str:
    return f"field:{tenant_id}:{draft_id}:{field_id}"


class AuthoringRepository:
    def __init__(
        self,
        settings: Settings,
        specifications: MessageSpecificationRegistry,
        profiles: ProfileRepository,
    ) -> None:
        self.settings = settings
        self.specifications = specifications
        self.profiles = profiles
        self.encryptor = EnvelopeEncryptor.from_settings(settings)

    def create_draft(
        self, user: SessionUser, message_type: MessageType, profile_id: str
    ) -> DraftResponse:
        profile = self.profiles.get(profile_id)
        specification = self.specifications.get(message_type)
        draft_id = str(uuid4())
        now = datetime.now(UTC)
        with SessionLocal() as session:
            draft = MessageDraftRecord(
                id=draft_id,
                tenant_id=user.tenant_id,
                message_type=message_type.value,
                profile_id=profile.profile_id,
                profile_version=profile.version,
                standards_release=specification.standards_release,
                status=DraftStatus.DRAFT.value,
                revision=1,
                created_by=user.user_id,
                validation_payload={},
                created_at=now,
                updated_at=now,
            )
            session.add(draft)
            instances_by_path: dict[str, DraftSequenceRecord] = {}
            for sequence in specification.sequences:
                if sequence.min_occurs == 0:
                    continue
                parent = instances_by_path.get(sequence.parent_path or "")
                instance = DraftSequenceRecord(
                    id=str(uuid4()),
                    draft_id=draft_id,
                    sequence_path=sequence.path,
                    parent_sequence_id=parent.id if parent else None,
                    occurrence=1,
                )
                session.add(instance)
                instances_by_path[sequence.path] = instance
            self._audit_session(
                session,
                user,
                "DRAFT_CREATED",
                "MESSAGE_DRAFT",
                draft_id,
                {"messageType": message_type.value, "profileId": profile_id},
            )
            session.commit()
        return self.get_draft(user, draft_id)

    def get_draft(self, user: SessionUser, draft_id: str) -> DraftResponse:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            sequences = list(
                session.scalars(
                    select(DraftSequenceRecord)
                    .where(DraftSequenceRecord.draft_id == draft_id)
                    .order_by(DraftSequenceRecord.sequence_path, DraftSequenceRecord.occurrence)
                )
            )
            fields = list(
                session.scalars(
                    select(DraftFieldRecord)
                    .where(DraftFieldRecord.draft_id == draft_id)
                    .order_by(DraftFieldRecord.created_at)
                )
            )
            specification = self.specifications.get(MessageType(draft.message_type))
            rows = {item.row_id: item for item in specification.fields}
            mask_sensitive = not bool(
                user.roles
                & {
                    PlatformRole.AUTHOR,
                    PlatformRole.REVIEWER,
                    PlatformRole.APPROVER,
                    PlatformRole.SUBMITTER,
                    PlatformRole.SECURITY_ADMIN,
                }
            )
            response_fields: list[DraftField] = []
            for field in fields:
                row = rows[field.row_id]
                classification = classify_field(row)
                value = self.encryptor.decrypt(
                    field.encrypted_value,
                    associated_data=_field_aad(user.tenant_id, draft_id, field.id),
                )
                masked = mask_sensitive and classification is DataClassification.FINANCIAL_SENSITIVE
                response_fields.append(
                    DraftField(
                        field_id=field.id,
                        sequence_id=field.sequence_id,
                        row_id=field.row_id,
                        value=mask_value(value) if masked else value,
                        masked=masked,
                        source=FieldValueSource(field.value_source),
                        confirmed=field.confirmed,
                        classification=classification,
                    )
                )
            validation_levels = {
                ValidationLevel(key): ValidationLevelState(value)
                for key, value in draft.validation_payload.get("levels", {}).items()
            }
            return DraftResponse(
                draft_id=draft.id,
                message_type=MessageType(draft.message_type),
                profile_id=draft.profile_id,
                profile_version=draft.profile_version,
                standards_release=draft.standards_release,
                capability=specification.capability,
                status=DraftStatus(draft.status),
                revision=draft.revision,
                created_by=draft.created_by,
                sequences=[
                    DraftSequence(
                        sequence_id=item.id,
                        sequence_path=item.sequence_path,
                        parent_sequence_id=item.parent_sequence_id,
                        occurrence=item.occurrence,
                    )
                    for item in sequences
                ],
                fields=response_fields,
                current_checksum=draft.current_checksum,
                validation_levels=validation_levels,
                created_at=draft.created_at,
                updated_at=draft.updated_at,
            )

    def update_profile(self, user: SessionUser, draft_id: str, profile_id: str) -> DraftResponse:
        profile = self.profiles.get(profile_id)
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            if draft.profile_id == profile.profile_id and draft.profile_version == profile.version:
                return self.get_draft(user, draft_id)
            draft.profile_id = profile.profile_id
            draft.profile_version = profile.version
            self._mark_edited(session, draft, user, "DRAFT_PROFILE_CHANGED")
            session.commit()
        return self.get_draft(user, draft_id)

    def add_sequence(
        self,
        user: SessionUser,
        draft_id: str,
        sequence_path: str,
        parent_sequence_id: str | None,
    ) -> DraftResponse:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            specification = self.specifications.get(MessageType(draft.message_type))
            sequence_spec = next(
                (item for item in specification.sequences if item.path == sequence_path), None
            )
            if sequence_spec is None:
                raise ValueError("The sequence is not configured for this message")
            parent = (
                session.get(DraftSequenceRecord, parent_sequence_id) if parent_sequence_id else None
            )
            if parent and parent.draft_id != draft_id:
                raise ValueError("The parent sequence does not belong to this draft")
            if sequence_spec.parent_path and (
                parent is None or parent.sequence_path != sequence_spec.parent_path
            ):
                raise ValueError("The required parent sequence was not supplied")
            if not sequence_spec.parent_path and parent is not None:
                raise ValueError("This top-level sequence cannot have a parent")
            existing = list(
                session.scalars(
                    select(DraftSequenceRecord).where(
                        DraftSequenceRecord.draft_id == draft_id,
                        DraftSequenceRecord.sequence_path == sequence_path,
                        DraftSequenceRecord.parent_sequence_id == parent_sequence_id,
                    )
                )
            )
            if len(existing) >= sequence_spec.max_occurs:
                raise ValueError("The configured sequence occurrence limit has been reached")
            session.add(
                DraftSequenceRecord(
                    id=str(uuid4()),
                    draft_id=draft_id,
                    sequence_path=sequence_path,
                    parent_sequence_id=parent_sequence_id,
                    occurrence=len(existing) + 1,
                )
            )
            self._mark_edited(session, draft, user, "SEQUENCE_ADDED")
            session.commit()
        return self.get_draft(user, draft_id)

    def remove_sequence(self, user: SessionUser, draft_id: str, sequence_id: str) -> DraftResponse:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            instance = session.get(DraftSequenceRecord, sequence_id)
            if instance is None or instance.draft_id != draft_id:
                raise KeyError(sequence_id)
            specification = self.specifications.get(MessageType(draft.message_type))
            sequence_spec = next(
                item for item in specification.sequences if item.path == instance.sequence_path
            )
            siblings = list(
                session.scalars(
                    select(DraftSequenceRecord).where(
                        DraftSequenceRecord.draft_id == draft_id,
                        DraftSequenceRecord.sequence_path == instance.sequence_path,
                        DraftSequenceRecord.parent_sequence_id == instance.parent_sequence_id,
                    )
                )
            )
            if len(siblings) <= sequence_spec.min_occurs:
                raise ValueError("A mandatory sequence occurrence cannot be removed")
            if session.scalar(
                select(DraftSequenceRecord.id).where(
                    DraftSequenceRecord.parent_sequence_id == sequence_id
                )
            ):
                raise ValueError("Remove child sequence occurrences first")
            session.execute(
                delete(DraftFieldRecord).where(DraftFieldRecord.sequence_id == sequence_id)
            )
            session.delete(instance)
            self._mark_edited(session, draft, user, "SEQUENCE_REMOVED")
            session.commit()
        return self.get_draft(user, draft_id)

    def upsert_field(
        self, user: SessionUser, draft_id: str, payload: FieldUpsertRequest
    ) -> DraftResponse:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            sequence = session.get(DraftSequenceRecord, payload.sequence_id)
            if sequence is None or sequence.draft_id != draft_id:
                raise ValueError("The sequence does not belong to this draft")
            specification = self.specifications.get(MessageType(draft.message_type))
            row = next(
                (item for item in specification.fields if item.row_id == payload.row_id), None
            )
            if row is None or row.sequence_path != sequence.sequence_path:
                raise ValueError("The field is not configured for this sequence")
            existing = session.scalar(
                select(DraftFieldRecord).where(
                    DraftFieldRecord.draft_id == draft_id,
                    DraftFieldRecord.sequence_id == payload.sequence_id,
                    DraftFieldRecord.row_id == payload.row_id,
                )
            )
            field_id = existing.id if existing else str(uuid4())
            encrypted = self.encryptor.encrypt(
                payload.value,
                associated_data=_field_aad(user.tenant_id, draft_id, field_id),
            )
            checksum = hashlib.sha256(payload.value.encode()).hexdigest()
            if existing:
                existing.encrypted_value = encrypted
                existing.value_checksum = checksum
                existing.value_source = payload.source.value
                existing.confirmed = payload.confirmed
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(
                    DraftFieldRecord(
                        id=field_id,
                        draft_id=draft_id,
                        sequence_id=payload.sequence_id,
                        row_id=payload.row_id,
                        encrypted_value=encrypted,
                        value_checksum=checksum,
                        value_source=payload.source.value,
                        confirmed=payload.confirmed,
                    )
                )
            self._mark_edited(session, draft, user, "FIELD_UPDATED")
            session.commit()
        return self.get_draft(user, draft_id)

    def delete_field(self, user: SessionUser, draft_id: str, field_id: str) -> DraftResponse:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            field = session.get(DraftFieldRecord, field_id)
            if field is None or field.draft_id != draft_id:
                raise KeyError(field_id)
            session.delete(field)
            self._mark_edited(session, draft, user, "FIELD_REMOVED")
            session.commit()
        return self.get_draft(user, draft_id)

    def load_for_composition(
        self, user: SessionUser, draft_id: str
    ) -> tuple[MessageDraftRecord, MessageSpecification, list[ComposeSequence], list[ComposeField]]:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            session.expunge(draft)
            specification = self.specifications.get(MessageType(draft.message_type))
            rows = {item.row_id: item for item in specification.fields}
            sequence_records = list(
                session.scalars(
                    select(DraftSequenceRecord).where(DraftSequenceRecord.draft_id == draft_id)
                )
            )
            field_records = list(
                session.scalars(
                    select(DraftFieldRecord).where(DraftFieldRecord.draft_id == draft_id)
                )
            )
            sequences = [
                ComposeSequence(
                    sequence_id=item.id,
                    sequence_path=item.sequence_path,
                    parent_sequence_id=item.parent_sequence_id,
                    occurrence=item.occurrence,
                )
                for item in sequence_records
            ]
            fields = [
                ComposeField(
                    row=rows[item.row_id],
                    sequence_id=item.sequence_id,
                    value=self.encryptor.decrypt(
                        item.encrypted_value,
                        associated_data=_field_aad(user.tenant_id, draft_id, item.id),
                    ),
                    source=FieldValueSource(item.value_source),
                    classification=classify_field(rows[item.row_id]),
                )
                for item in field_records
            ]
            return draft, specification, sequences, fields

    def save_composition(
        self,
        user: SessionUser,
        draft_id: str,
        checksum: str,
        validation_levels: dict[ValidationLevel, ValidationLevelState],
        findings: list[str],
        snapshot: dict[str, object],
    ) -> None:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            previous_status = draft.status
            previous_checksum = draft.current_checksum
            draft.current_checksum = checksum
            draft.validation_payload = {
                "levels": {key.value: value.value for key, value in validation_levels.items()},
                "findingCount": len(findings),
            }
            local_passed = all(
                validation_levels[level] is ValidationLevelState.PASSED
                for level in (
                    ValidationLevel.CANONICAL_VALID,
                    ValidationLevel.STRUCTURE_VALID,
                    ValidationLevel.FORMAT_VALID,
                    ValidationLevel.CLIENT_PROFILE_VALID,
                )
            )
            if (
                previous_status in {DraftStatus.REVIEW_REQUESTED.value, DraftStatus.APPROVED.value}
                and previous_checksum == checksum
                and local_passed
            ):
                draft.status = previous_status
            else:
                draft.status = (
                    DraftStatus.VALIDATED.value if local_passed else DraftStatus.DRAFT.value
                )
            encrypted_snapshot = self.encryptor.encrypt(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                associated_data=f"snapshot:{user.tenant_id}:{draft_id}:{draft.revision}",
            )
            existing = session.scalar(
                select(DraftVersionRecord).where(
                    DraftVersionRecord.draft_id == draft_id,
                    DraftVersionRecord.revision == draft.revision,
                )
            )
            if existing is None:
                session.add(
                    DraftVersionRecord(
                        id=str(uuid4()),
                        draft_id=draft_id,
                        revision=draft.revision,
                        checksum=checksum,
                        encrypted_snapshot=encrypted_snapshot,
                        created_by=user.user_id,
                    )
                )
            else:
                existing.checksum = checksum
                existing.encrypted_snapshot = encrypted_snapshot
            self._audit_session(
                session,
                user,
                "MESSAGE_COMPOSED",
                "MESSAGE_DRAFT",
                draft_id,
                {"revision": draft.revision, "checksum": checksum},
            )
            session.commit()

    def request_review(self, user: SessionUser, draft_id: str) -> MessageDraftRecord:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            if draft.status != DraftStatus.VALIDATED.value:
                raise ValueError("A locally validated immutable revision is required")
            draft.status = DraftStatus.REVIEW_REQUESTED.value
            session.add(
                MessageReviewRecord(
                    id=str(uuid4()),
                    draft_id=draft_id,
                    revision=draft.revision,
                    requested_by=user.user_id,
                    status="REQUESTED",
                )
            )
            self._audit_session(session, user, "REVIEW_REQUESTED", "MESSAGE_DRAFT", draft_id, {})
            session.commit()
            session.refresh(draft)
            session.expunge(draft)
            return draft

    def approve(self, user: SessionUser, draft_id: str) -> MessageApprovalRecord:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            assert draft is not None
            if draft.status != DraftStatus.REVIEW_REQUESTED.value:
                raise ValueError("The draft is not awaiting review")
            if draft.created_by == user.user_id:
                raise ValueError("Maker-checker policy forbids self-approval")
            if not draft.current_checksum:
                raise ValueError("The approved revision requires a checksum")
            approval = MessageApprovalRecord(
                id=str(uuid4()),
                draft_id=draft_id,
                revision=draft.revision,
                message_checksum=draft.current_checksum,
                approved_by=user.user_id,
                active=True,
            )
            session.add(approval)
            draft.status = DraftStatus.APPROVED.value
            session.execute(
                update(MessageReviewRecord)
                .where(
                    MessageReviewRecord.draft_id == draft_id,
                    MessageReviewRecord.revision == draft.revision,
                )
                .values(status="APPROVED")
            )
            self._audit_session(
                session,
                user,
                "MESSAGE_APPROVED",
                "MESSAGE_DRAFT",
                draft_id,
                {"revision": draft.revision, "checksum": draft.current_checksum},
            )
            session.commit()
            session.refresh(approval)
            session.expunge(approval)
            return approval

    def list_audit(self, user: SessionUser, draft_id: str) -> list[AuditEventResponse]:
        with SessionLocal() as session:
            draft = session.get(MessageDraftRecord, draft_id)
            self._require_tenant(draft, user)
            events = list(
                session.scalars(
                    select(PlatformAuditRecord)
                    .where(
                        PlatformAuditRecord.tenant_id == user.tenant_id,
                        PlatformAuditRecord.resource_id == draft_id,
                    )
                    .order_by(PlatformAuditRecord.created_at)
                )
            )
            return [
                AuditEventResponse(
                    event_id=item.id,
                    action=item.action,
                    resource_type=item.resource_type,
                    resource_id=item.resource_id,
                    actor_id=item.actor_id,
                    safe_metadata=item.safe_metadata,
                    created_at=item.created_at,
                )
                for item in events
            ]

    @staticmethod
    def _require_tenant(draft: MessageDraftRecord | None, user: SessionUser) -> None:
        if draft is None or draft.tenant_id != user.tenant_id:
            raise KeyError("draft")

    def _mark_edited(
        self,
        session: Session,
        draft: MessageDraftRecord,
        user: SessionUser,
        action: str,
    ) -> None:
        now = datetime.now(UTC)
        draft.revision += 1
        draft.status = DraftStatus.DRAFT.value
        draft.current_checksum = None
        draft.validation_payload = {}
        draft.updated_at = now
        session.execute(
            update(MessageApprovalRecord)
            .where(MessageApprovalRecord.draft_id == draft.id, MessageApprovalRecord.active)
            .values(active=False, invalidated_at=now)
        )
        self._audit_session(
            session,
            user,
            action,
            "MESSAGE_DRAFT",
            draft.id,
            {"revision": draft.revision, "approvalInvalidated": True},
        )

    @staticmethod
    def _audit_session(
        session: Session,
        user: SessionUser,
        action: str,
        resource_type: str,
        resource_id: str,
        safe_metadata: dict[str, object],
    ) -> None:
        session.add(
            PlatformAuditRecord(
                id=str(uuid4()),
                tenant_id=user.tenant_id,
                actor_id=user.user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                safe_metadata=safe_metadata,
            )
        )
