"""Allow workflow-level report artifacts without a settlement scenario."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0005"
down_revision: str | None = "20260805_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch_op:
        batch_op.alter_column(
            "scenario_id",
            existing_type=sa.String(36),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch_op:
        batch_op.alter_column(
            "scenario_id",
            existing_type=sa.String(36),
            nullable=False,
        )
