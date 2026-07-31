"""fix item_price EXCLUDE constraint: NULL location_code never conflicts

Found live: POSTing two overlapping network prices (location_code IS NULL)
for the same item both succeeded — the constraint added in
0002_item_price_location_scope.py silently does not do what its own
comment claims.

PostgreSQL exclusion constraints treat a NULL in an operator column as
distinct from every other value, including another NULL (this is
documented, unrelated-column-comment notwithstanding — the same rule as
a plain UNIQUE index before PG15's NULLS NOT DISTINCT, but exclusion
constraints have no NULLS NOT DISTINCT escape hatch). So
`location_code WITH =` never reports a conflict when location_code is
NULL on either row, and two "network price" rows for the same item with
overlapping effective ranges are both accepted — exactly the ambiguity
core.item_price exists to prevent (SPEC §4.3, open item #2).

Fixed with the standard workaround: compare COALESCE(location_code, '')
instead, so two NULLs collide as equal while any real location_code still
only conflicts with itself.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.item_price
            DROP CONSTRAINT item_price_item_location_daterange_excl;

        ALTER TABLE core.item_price
            ADD CONSTRAINT item_price_item_location_daterange_excl
            EXCLUDE USING gist (
                item_code WITH =,
                COALESCE(location_code, '') WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE core.item_price
            DROP CONSTRAINT item_price_item_location_daterange_excl;

        ALTER TABLE core.item_price
            ADD CONSTRAINT item_price_item_location_daterange_excl
            EXCLUDE USING gist (
                item_code WITH =,
                location_code WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
    """)
