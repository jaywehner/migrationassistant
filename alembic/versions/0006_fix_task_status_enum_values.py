"""Normalize task status enum punctuation

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'taskstatus' AND e.enumlabel = 'Closed – Not Needed'
            ) THEN
                ALTER TYPE taskstatus RENAME VALUE 'Closed – Not Needed' TO 'Closed - Not Needed';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'taskstatus' AND e.enumlabel = 'Closed – Complete'
            ) THEN
                ALTER TYPE taskstatus RENAME VALUE 'Closed – Complete' TO 'Closed - Complete';
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'taskstatus' AND e.enumlabel = 'Closed - Not Needed'
            ) THEN
                ALTER TYPE taskstatus RENAME VALUE 'Closed - Not Needed' TO 'Closed – Not Needed';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'taskstatus' AND e.enumlabel = 'Closed - Complete'
            ) THEN
                ALTER TYPE taskstatus RENAME VALUE 'Closed - Complete' TO 'Closed – Complete';
            END IF;
        END
        $$;
    """)
