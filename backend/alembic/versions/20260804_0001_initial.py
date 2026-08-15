"""Initial Securities Settlement Message Studio schema."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("standards_release", sa.String(32), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("canonical_data", sa.JSON(), nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("direction", sa.String(24)),
        sa.Column("payment_type", sa.String(32)),
        sa.Column("message_type", sa.String(8), nullable=False),
        sa.Column("generation_mode", sa.String(24), nullable=False),
        sa.Column("synthetic_data", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scenarios_scenario_id", "scenarios", ["scenario_id"])
    op.create_index("ix_scenarios_profile_id", "scenarios", ["profile_id"])
    op.create_index("ix_scenarios_lifecycle", "scenarios", ["lifecycle"])
    op.create_index("ix_scenarios_message_type", "scenarios", ["message_type"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id")),
        sa.Column("message_type", sa.String(8), nullable=False),
        sa.Column("raw_message", sa.Text(), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=False),
        sa.Column("related_message_id", sa.String(36), sa.ForeignKey("messages.id")),
        sa.Column("sender_reference", sa.String(64), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.String(32), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_scenario_id", "messages", ["scenario_id"])
    op.create_index("ix_messages_message_type", "messages", ["message_type"])
    op.create_index("ix_messages_related_message_id", "messages", ["related_message_id"])
    op.create_index("ix_messages_sender_reference", "messages", ["sender_reference"])
    op.create_table(
        "validation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("field_path", sa.String(128)),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("technical_explanation", sa.Text(), nullable=False),
        sa.Column("current_value", sa.JSON()),
        sa.Column("expected_condition", sa.Text()),
        sa.Column("suggestion", sa.Text()),
        sa.Column("intentional", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_results_message_id", "validation_results", ["message_id"])
    op.create_index("ix_validation_results_rule_id", "validation_results", ["rule_id"])
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("artifact_path", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_scenario_id", "reports", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_scenario_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_validation_results_rule_id", table_name="validation_results")
    op.drop_index("ix_validation_results_message_id", table_name="validation_results")
    op.drop_table("validation_results")
    op.drop_index("ix_messages_sender_reference", table_name="messages")
    op.drop_index("ix_messages_related_message_id", table_name="messages")
    op.drop_index("ix_messages_message_type", table_name="messages")
    op.drop_index("ix_messages_scenario_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_scenarios_message_type", table_name="scenarios")
    op.drop_index("ix_scenarios_lifecycle", table_name="scenarios")
    op.drop_index("ix_scenarios_profile_id", table_name="scenarios")
    op.drop_index("ix_scenarios_scenario_id", table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_table("profiles")
