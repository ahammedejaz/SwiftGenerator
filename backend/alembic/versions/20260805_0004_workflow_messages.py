"""Add generic workflow-message persistence for pluggable modules."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0004"
down_revision: str | None = "20260805_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("workflow_module", sa.String(48), nullable=False),
        sa.Column("message_type", sa.String(8), nullable=False),
        sa.Column("canonical_data", sa.JSON(), nullable=False),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("validation_payload", sa.JSON(), nullable=False),
        sa.Column(
            "related_workflow_message_id", sa.String(36), sa.ForeignKey("workflow_messages.id")
        ),
        sa.Column("related_settlement_message_id", sa.String(36), sa.ForeignKey("messages.id")),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "workflow_id",
        "workflow_module",
        "message_type",
        "profile_id",
        "related_workflow_message_id",
        "related_settlement_message_id",
    ):
        op.create_index(f"ix_workflow_messages_{column}", "workflow_messages", [column])


def downgrade() -> None:
    for column in reversed(
        (
            "workflow_id",
            "workflow_module",
            "message_type",
            "profile_id",
            "related_workflow_message_id",
            "related_settlement_message_id",
        )
    ):
        op.drop_index(f"ix_workflow_messages_{column}", table_name="workflow_messages")
    op.drop_table("workflow_messages")
