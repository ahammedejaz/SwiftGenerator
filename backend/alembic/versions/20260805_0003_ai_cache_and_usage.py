"""Add privacy-safe AI result cache and efficiency interaction metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0003"
down_revision: str | None = "20260804_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_result_cache",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("namespace", sa.String(48), nullable=False),
        sa.Column("key_version", sa.String(16), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("knowledge_version", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("workflow_module", sa.String(48), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("standards_release", sa.String(64), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("reported_cost", sa.String(40)),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("escalation_reason", sa.String(64)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("schema_retries", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_ai_result_cache_namespace", "ai_result_cache", ["namespace"])
    op.create_index("ix_ai_result_cache_profile_id", "ai_result_cache", ["profile_id"])
    op.create_index("ix_ai_result_cache_expires_at", "ai_result_cache", ["expires_at"])

    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("interaction_id", sa.String(36), nullable=False, unique=True),
        sa.Column("operation_type", sa.String(48), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(128)),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("cache_namespace", sa.String(48)),
        sa.Column("cache_entry_age_seconds", sa.Integer()),
        sa.Column("live_api_call_count", sa.Integer(), nullable=False),
        sa.Column("primary_call_count", sa.Integer(), nullable=False),
        sa.Column("escalation_call_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("reported_cost", sa.String(40)),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_avoided", sa.Integer(), nullable=False),
        sa.Column("calls_avoided", sa.Integer(), nullable=False),
        sa.Column("cost_avoided", sa.String(40)),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("knowledge_version", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32)),
        sa.Column("outcome_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_interactions_interaction_id",
        "ai_interactions",
        ["interaction_id"],
        unique=True,
    )
    op.create_index("ix_ai_interactions_operation_type", "ai_interactions", ["operation_type"])
    op.create_index("ix_ai_interactions_source", "ai_interactions", ["source"])
    op.create_index("ix_ai_interactions_cache_hit", "ai_interactions", ["cache_hit"])
    op.create_index("ix_ai_interactions_outcome_code", "ai_interactions", ["outcome_code"])


def downgrade() -> None:
    op.drop_index("ix_ai_interactions_outcome_code", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_cache_hit", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_source", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_operation_type", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_interaction_id", table_name="ai_interactions")
    op.drop_table("ai_interactions")
    op.drop_index("ix_ai_result_cache_expires_at", table_name="ai_result_cache")
    op.drop_index("ix_ai_result_cache_profile_id", table_name="ai_result_cache")
    op.drop_index("ix_ai_result_cache_namespace", table_name="ai_result_cache")
    op.drop_table("ai_result_cache")
