"""Add content-free OpenRouter interpretation audit metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0002"
down_revision: str | None = "20260804_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_interpretation_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("scenario_id", sa.String(64)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("primary_model", sa.String(128), nullable=False),
        sa.Column("final_model", sa.String(128)),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("escalation_reason", sa.String(64)),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("reported_cost", sa.String(40)),
        sa.Column("outcome_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_interpretation_audit_request_id",
        "ai_interpretation_audit",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        "ix_ai_interpretation_audit_scenario_id",
        "ai_interpretation_audit",
        ["scenario_id"],
    )
    op.create_index(
        "ix_ai_interpretation_audit_outcome_code",
        "ai_interpretation_audit",
        ["outcome_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_interpretation_audit_outcome_code",
        table_name="ai_interpretation_audit",
    )
    op.drop_index(
        "ix_ai_interpretation_audit_scenario_id",
        table_name="ai_interpretation_audit",
    )
    op.drop_index(
        "ix_ai_interpretation_audit_request_id",
        table_name="ai_interpretation_audit",
    )
    op.drop_table("ai_interpretation_audit")
