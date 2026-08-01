"""add core.stock_movement.confirmed_by_name

Receiving needs to capture who physically handled a delivery, which is
often not the same person as the logged-in device/account that submitted
it (a shared branch tablet, for instance). created_by already answers
"which system account wrote this row" (CLAUDE.md ACCESS: every write sets
session context); this answers "which person, if different, actually
confirmed it" — a free-text field, deliberately not a core.app_user FK,
since the physical receiver isn't necessarily a system user at all.

Generic on the table (not receiving-specific in the schema), same as
source_code/ref_doc_type already are — only Receiving populates it today,
but nothing here assumes that stays true.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE core.stock_movement ADD COLUMN confirmed_by_name VARCHAR(255);")


def downgrade() -> None:
    op.execute("ALTER TABLE core.stock_movement DROP COLUMN IF EXISTS confirmed_by_name;")
