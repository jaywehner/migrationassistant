"""Add task position for ordering

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill: number existing tasks 1..N within each tab by creation time
    op.execute(
        """
        UPDATE tasks t SET position = sub.rn FROM (
            SELECT id, row_number() OVER (PARTITION BY tab_id ORDER BY created_at) AS rn
            FROM tasks
        ) sub WHERE t.id = sub.id
        """
    )


def downgrade() -> None:
    op.drop_column("tasks", "position")
