"""add approved_by/approved_at to count_session

Found while building the counts endpoint: SPEC §7.4's separation-of-duties
rule ("the user who records a stock adjustment cannot approve their own
count variance above a configurable threshold") needs somewhere to record
who approved a count and when, exactly mirroring submitted_by/submitted_at.
core.count_session had neither — approval had no column to write to, which
means the rule could not be enforced *or audited* no matter how the service
layer was written.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.count_session
            ADD COLUMN approved_at TIMESTAMPTZ,
            ADD COLUMN approved_by BIGINT;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core.count_session
            DROP COLUMN IF EXISTS approved_at,
            DROP COLUMN IF EXISTS approved_by;
    """)
