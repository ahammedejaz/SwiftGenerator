from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ProfileRecord(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    standards_release: Mapped[str] = mapped_column(String(32))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScenarioRecord(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    profile_version: Mapped[str] = mapped_column(String(32))
    canonical_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    lifecycle: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str | None] = mapped_column(String(24))
    payment_type: Mapped[str | None] = mapped_column(String(32))
    message_type: Mapped[str] = mapped_column(String(8), index=True)
    generation_mode: Mapped[str] = mapped_column(String(24))
    synthetic_data: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    messages: Mapped[list["MessageRecord"]] = relationship(back_populates="scenario")


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(8), index=True)
    raw_message: Mapped[str] = mapped_column(Text)
    field_map: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    related_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    sender_reference: Mapped[str] = mapped_column(String(64), index=True)
    validation_status: Mapped[str] = mapped_column(String(32))
    profile_id: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str] = mapped_column(String(32))
    disclaimer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    scenario: Mapped[ScenarioRecord] = relationship(back_populates="messages")
    findings: Mapped[list["ValidationResultRecord"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class ValidationResultRecord(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    field_path: Mapped[str | None] = mapped_column(String(128))
    message_text: Mapped[str] = mapped_column("message", Text)
    technical_explanation: Mapped[str] = mapped_column(Text)
    current_value: Mapped[Any | None] = mapped_column(JSON)
    expected_condition: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    intentional: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    message: Mapped[MessageRecord] = relationship(back_populates="findings")


class ReportRecord(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id"), index=True, nullable=True
    )
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AiAuditRecord(Base):
    __tablename__ = "ai_interpretation_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    primary_model: Mapped[str] = mapped_column(String(128))
    final_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    reported_cost: Mapped[str | None] = mapped_column(String(40), nullable=True)
    outcome_code: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AiCacheRecord(Base):
    __tablename__ = "ai_result_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(48), index=True)
    key_version: Mapped[str] = mapped_column(String(16))
    prompt_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    knowledge_version: Mapped[str] = mapped_column(String(64))
    taxonomy_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    workflow_module: Mapped[str] = mapped_column(String(48))
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    profile_version: Mapped[str] = mapped_column(String(32))
    standards_release: Mapped[str] = mapped_column(String(64))
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    reported_cost: Mapped[str | None] = mapped_column(String(40), nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer)
    schema_retries: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class AiInteractionRecord(Base):
    __tablename__ = "ai_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(48), index=True)
    source: Mapped[str] = mapped_column(String(24), index=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cache_namespace: Mapped[str | None] = mapped_column(String(48), nullable=True)
    cache_entry_age_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_api_call_count: Mapped[int] = mapped_column(Integer, default=0)
    primary_call_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation_call_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reported_cost: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_avoided: Mapped[int] = mapped_column(Integer, default=0)
    calls_avoided: Mapped[int] = mapped_column(Integer, default=0)
    cost_avoided: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    knowledge_version: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_code: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkflowMessageRecord(Base):
    __tablename__ = "workflow_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True)
    workflow_module: Mapped[str] = mapped_column(String(48), index=True)
    message_type: Mapped[str] = mapped_column(String(8), index=True)
    canonical_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_message: Mapped[str] = mapped_column(Text)
    field_map: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    profile_version: Mapped[str] = mapped_column(String(32))
    validation_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    related_workflow_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_messages.id"), nullable=True, index=True
    )
    related_settlement_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    disclaimer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TenantRecord(Base):
    __tablename__ = "platform_tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlatformUserRecord(Base):
    __tablename__ = "platform_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    subject: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserRoleRecord(Base):
    __tablename__ = "platform_user_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("platform_users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)


class PlatformSessionRecord(Base):
    __tablename__ = "platform_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("platform_users.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageDraftRecord(Base):
    __tablename__ = "message_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(8), index=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    profile_version: Mapped[str] = mapped_column(String(32))
    standards_release: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"), index=True)
    current_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DraftSequenceRecord(Base):
    __tablename__ = "draft_sequences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    sequence_path: Mapped[str] = mapped_column(String(96), index=True)
    parent_sequence_id: Mapped[str | None] = mapped_column(
        ForeignKey("draft_sequences.id"), nullable=True, index=True
    )
    occurrence: Mapped[int] = mapped_column(Integer)


class DraftFieldRecord(Base):
    __tablename__ = "draft_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("draft_sequences.id"), index=True)
    row_id: Mapped[str] = mapped_column(String(160), index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    value_checksum: Mapped[str] = mapped_column(String(64))
    value_source: Mapped[str] = mapped_column(String(32))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DraftVersionRecord(Base):
    __tablename__ = "draft_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_snapshot: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageReviewRecord(Base):
    __tablename__ = "message_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    status: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageApprovalRecord(Base):
    __tablename__ = "message_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    message_checksum: Mapped[str] = mapped_column(String(64), index=True)
    approved_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConnectorRecord(Base):
    __tablename__ = "submission_connectors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    connector_type: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16), index=True)
    capability: Mapped[str] = mapped_column(String(32))
    destination_alias: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    safe_configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SubmissionRecord(Base):
    __tablename__ = "message_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    connector_id: Mapped[str] = mapped_column(ForeignKey("submission_connectors.id"), index=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    message_checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    provider_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    client_correlation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    safe_response_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledgement_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SubmissionAttemptRecord(Base):
    __tablename__ = "submission_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("message_submissions.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome_code: Mapped[str] = mapped_column(String(64))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ExternalValidationRecord(Base):
    __tablename__ = "external_validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("message_drafts.id"), index=True)
    message_checksum: Mapped[str] = mapped_column(String(64), index=True)
    provider_type: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[str] = mapped_column(String(64))
    standards_release: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    safe_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_by: Mapped[str] = mapped_column(ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlatformAuditRecord(Base):
    __tablename__ = "platform_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("platform_tenants.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("platform_users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(48), index=True)
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
