"""add is_active to reference tables missing it

Found while building the reference-data CRUD endpoints (SPEC §5.6/§5.7):
the delete policy table names "Soft" (deactivate, never hard-delete) for
core.item_category, core.area, core.cluster, core.route and core.uom, but
none of the five actually has an is_active column — only core.reason_code
does. Without it, "deactivate" as promised by SPEC §5.7 rule 1 ("every
reference table gets full CRUD... deactivation only") is not implementable
for five of the six tables the Reference Data screen covers.

DEFAULT TRUE on an existing column is additive and lossless — every
existing row becomes active, which is correct (nothing was ever meant to
be deactivated retroactively by this migration).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["item_category", "area", "cluster", "route", "uom"]


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"ALTER TABLE core.{table} ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE core.{table} DROP COLUMN is_active")
