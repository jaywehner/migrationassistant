"""Widen task_steps.title to Text for rich content

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "task_steps", "title",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "task_steps", "title",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
