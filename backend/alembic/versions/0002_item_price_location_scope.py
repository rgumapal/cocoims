"""item_price location scope + app_user role_hint

The client's seed data (db/seed/002_client_data.sql) surfaces a real conflict
in the source workbook: SRP disagrees between the network-wide "Pillow Pack
Sched" sheet and individual store tabs for several items (e.g. Double Cheese
Roll 15 vs 18). Rather than guessing which is right, the seed records both —
a CONFIRMED network price (location_code NULL) and a PENDING_REVIEW candidate
branch override — which needs core.item_price to be location-scoped and
status-tracked. This wasn't in SPEC §4.3's literal DDL; it's a schema
extension driven by data actually seen in the client's workbook, matching the
spec's own DQ principle: never discard or silently resolve ambiguous data.

core.app_user.role_hint is a small informational add: a human-readable label
for seed/display convenience. Actual authorization is still entirely via
core.user_role — role_hint is never read for access decisions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.item_price
            ADD COLUMN location_code VARCHAR(10) REFERENCES core.location(location_code),
            ADD COLUMN price_status VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
            ADD COLUMN note TEXT,
            ADD CONSTRAINT chk_item_price_status
                CHECK (price_status IN ('CONFIRMED', 'PENDING_REVIEW', 'SUPERSEDED'));
    """)

    # Re-scope the EXCLUDE constraint to (item_code, location_code) instead of
    # item_code alone, so a NULL "network" row and a branch-specific override
    # for the same item/date-range can coexist. NULLs are not distinct from
    # each other under GiST exclusion (same as a plain UNIQUE index pre-PG15's
    # NULLS NOT DISTINCT), so this still caps at most one active network price
    # per item — which is the intended behaviour.
    op.execute("""
        ALTER TABLE core.item_price
            DROP CONSTRAINT item_price_item_code_daterange_excl;
    """)
    op.execute("""
        ALTER TABLE core.item_price
            ADD CONSTRAINT item_price_item_location_daterange_excl
            EXCLUDE USING gist (
                item_code WITH =,
                location_code WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
    """)

    # A branch-specific CONFIRMED row wins over the network row for that
    # branch; falls back to the network (location_code IS NULL) row otherwise.
    # Referenced directly in db/seed/002_client_data.sql's verification query.
    op.execute("""
        CREATE OR REPLACE VIEW core.v_effective_price AS
        SELECT DISTINCT ON (l.location_code, p.item_code)
            l.location_code, p.item_code, p.srp, p.unit_cost, p.price_id
        FROM core.location l
        CROSS JOIN core.item_price p
        WHERE p.price_status = 'CONFIRMED'
          AND (p.location_code = l.location_code OR p.location_code IS NULL)
          AND p.effective_from <= CURRENT_DATE
          AND (p.effective_to IS NULL OR p.effective_to > CURRENT_DATE)
        ORDER BY l.location_code, p.item_code, p.location_code NULLS LAST;
    """)

    op.execute("ALTER TABLE core.app_user ADD COLUMN role_hint VARCHAR(30);")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS core.v_effective_price;")
    op.execute("ALTER TABLE core.app_user DROP COLUMN IF EXISTS role_hint;")
    op.execute("""
        ALTER TABLE core.item_price
            DROP CONSTRAINT IF EXISTS item_price_item_location_daterange_excl;
    """)
    op.execute("""
        ALTER TABLE core.item_price
            ADD CONSTRAINT item_price_item_code_daterange_excl
            EXCLUDE USING gist (
                item_code WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
    """)
    op.execute("""
        ALTER TABLE core.item_price
            DROP CONSTRAINT IF EXISTS chk_item_price_status,
            DROP COLUMN IF EXISTS location_code,
            DROP COLUMN IF EXISTS price_status,
            DROP COLUMN IF EXISTS note;
    """)
