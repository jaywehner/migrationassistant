"""Add global admin fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Explicitly create the enum type first for PostgreSQL
    global_access_level_enum = sa.Enum("admin", "user", "read_only", name="globalaccesslevel")
    global_access_level_enum.create(op.get_bind(), checkfirst=True)

    # Add global_access_level enum column
    op.add_column(
        "users",
        sa.Column(
            "global_access_level",
            global_access_level_enum,
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column(
        "users",
        sa.Column("is_global_admin", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("is_first_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_first_admin")
    op.drop_column("users", "is_global_admin")
    op.drop_column("users", "global_access_level")
    sa.Enum("admin", "user", "read_only", name="globalaccesslevel").drop(op.get_bind(), checkfirst=True)
