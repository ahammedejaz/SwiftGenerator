"""Add tenant-scoped encrypted authoring and controlled-submission records."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0006"
down_revision: str | None = "20260805_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "platform_tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "platform_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_platform_users_tenant_id", "platform_users", ["tenant_id"])
    op.create_index("ix_platform_users_subject", "platform_users", ["subject"], unique=True)
    op.create_table(
        "platform_user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
    )
    op.create_index("ix_platform_user_roles_user_id", "platform_user_roles", ["user_id"])
    op.create_index("ix_platform_user_roles_role", "platform_user_roles", ["role"])
    op.create_table(
        "platform_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_platform_sessions_user_id", "platform_sessions", ["user_id"])
    op.create_index("ix_platform_sessions_expires_at", "platform_sessions", ["expires_at"])
    op.create_table(
        "message_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("message_type", sa.String(8), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("standards_release", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("current_checksum", sa.String(64), nullable=True),
        sa.Column("validation_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("tenant_id", "message_type", "profile_id", "status", "created_by"):
        op.create_index(f"ix_message_drafts_{column}", "message_drafts", [column])
    op.create_table(
        "draft_sequences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("sequence_path", sa.String(96), nullable=False),
        sa.Column(
            "parent_sequence_id", sa.String(36), sa.ForeignKey("draft_sequences.id"), nullable=True
        ),
        sa.Column("occurrence", sa.Integer(), nullable=False),
    )
    for column in ("draft_id", "sequence_path", "parent_sequence_id"):
        op.create_index(f"ix_draft_sequences_{column}", "draft_sequences", [column])
    op.create_table(
        "draft_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column(
            "sequence_id", sa.String(36), sa.ForeignKey("draft_sequences.id"), nullable=False
        ),
        sa.Column("row_id", sa.String(160), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("value_checksum", sa.String(64), nullable=False),
        sa.Column("value_source", sa.String(32), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("draft_id", "sequence_id", "row_id"):
        op.create_index(f"ix_draft_fields_{column}", "draft_fields", [column])
    op.create_table(
        "draft_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("encrypted_snapshot", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("draft_id", "revision", name="uq_draft_versions_revision"),
    )
    op.create_index("ix_draft_versions_draft_id", "draft_versions", ["draft_id"])
    op.create_index("ix_draft_versions_checksum", "draft_versions", ["checksum"])
    op.create_table(
        "message_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "requested_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False
        ),
        sa.Column("status", sa.String(24), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_message_reviews_draft_id", "message_reviews", ["draft_id"])
    op.create_index("ix_message_reviews_status", "message_reviews", ["status"])
    op.create_table(
        "message_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("message_checksum", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("draft_id", "message_checksum", "active"):
        op.create_index(f"ix_message_approvals_{column}", "message_approvals", [column])
    op.create_table(
        "submission_connectors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("connector_type", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("destination_alias", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("safe_configuration", sa.JSON(), nullable=False),
    )
    op.create_index("ix_submission_connectors_tenant_id", "submission_connectors", ["tenant_id"])
    op.create_index(
        "ix_submission_connectors_environment", "submission_connectors", ["environment"]
    )
    op.create_table(
        "message_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "connector_id", sa.String(64), sa.ForeignKey("submission_connectors.id"), nullable=False
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("message_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "submitted_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False
        ),
        sa.Column("provider_message_id", sa.String(160), nullable=True),
        sa.Column("client_correlation_id", sa.String(160), nullable=True),
        sa.Column("safe_response_code", sa.String(64), nullable=True),
        sa.Column("acknowledgement_reference", sa.String(160), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("tenant_id", "draft_id", "connector_id", "message_checksum", "status"):
        op.create_index(f"ix_message_submissions_{column}", "message_submissions", [column])
    op.create_table(
        "submission_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id", sa.String(36), sa.ForeignKey("message_submissions.id"), nullable=False
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome_code", sa.String(64), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "ix_submission_attempts_submission_id", "submission_attempts", ["submission_id"]
    )
    op.create_table(
        "external_validation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("message_drafts.id"), nullable=False),
        sa.Column("message_checksum", sa.String(64), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("standards_release", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_findings", sa.JSON(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=False),
        *_timestamps(),
    )
    for column in ("tenant_id", "draft_id", "message_checksum", "status"):
        op.create_index(
            f"ix_external_validation_results_{column}", "external_validation_results", [column]
        )
    op.create_table(
        "platform_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("platform_tenants.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("platform_users.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(48), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    for column in ("tenant_id", "actor_id", "action", "resource_type", "resource_id"):
        op.create_index(f"ix_platform_audit_events_{column}", "platform_audit_events", [column])


def downgrade() -> None:
    for table in (
        "platform_audit_events",
        "external_validation_results",
        "submission_attempts",
        "message_submissions",
        "submission_connectors",
        "message_approvals",
        "message_reviews",
        "draft_versions",
        "draft_fields",
        "draft_sequences",
        "message_drafts",
        "platform_sessions",
        "platform_user_roles",
        "platform_users",
        "platform_tenants",
    ):
        op.drop_table(table)
