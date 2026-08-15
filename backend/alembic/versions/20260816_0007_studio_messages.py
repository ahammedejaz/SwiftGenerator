"""Add the Financial Message Studio recent-messages table.

Additive and non-destructive: it creates one new table and touches nothing that already
exists, so it can be applied to a populated database safely.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0007"
down_revision: str | None = "20260805_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("scenario_id", sa.String(64), nullable=True),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("outputs_json", sa.Text(), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_studio_messages_created_at", "studio_messages", ["created_at"])
    op.create_index("ix_studio_messages_format", "studio_messages", ["format"])
    op.create_index("ix_studio_messages_message_type", "studio_messages", ["message_type"])


def downgrade() -> None:
    op.drop_index("ix_studio_messages_message_type", table_name="studio_messages")
    op.drop_index("ix_studio_messages_format", table_name="studio_messages")
    op.drop_index("ix_studio_messages_created_at", table_name="studio_messages")
    op.drop_table("studio_messages")
