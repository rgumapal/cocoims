"""sales.record permission + core.sold_out_event

Two gaps surfaced by a real client requirement (Stock IN/OUT/Sold/Transfers/
Excess/Run Outs — see the project's Sales entry work): recording a sale was
never a permission-gated action at all (no `sales.record` row existed in the
RBAC seed — receiving/waste both have their own `*.record`/`*.confirm`
permission, sales had none), and there was no signal anywhere for "this
branch/item ran out" — the fact the Run Outs metric needs.

sales.record is granted to the same four roles as waste.record
(SYS_ADMIN/OPS_MANAGER/STORE_HEAD/STORE_TEAM): recording today's sales is
the same kind of store-level daily capture task as recording waste, not a
new authority tier. SYS_ADMIN needs an explicit grant row here too — the
blanket "SYS_ADMIN gets every permission" INSERT in db/seed/002_client_data.sql
already ran once during initial seeding and won't retroactively pick up a
permission created by a later migration.

core.sold_out_event is a new, deliberately small table rather than folding a
"sold out" boolean onto core.stock_movement: a sold-out event is a fact
about a (business_date, location, item) combination, not a quantity
movement, and stock_movement's append-only/immutable rigor (migration 0004)
is calibrated for the financial ledger, not a lightweight operational flag
that store staff may legitimately need to correct. It gets the same
scope_by_location RLS shape as core.count_session (SPEC §7.2 rule 3) since
it's branch-scoped operational data written by the same store-level roles.
No audit trigger: CLAUDE.md's audit-trigger rule targets master/reference/
parameter tables, and this is an event log, not reference data.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO core.permission (permission_code, resource, action, label, is_destructive)
        VALUES ('sales.record', 'sales', 'record', 'Record sales (offtake)', FALSE)
        ON CONFLICT DO NOTHING;

        INSERT INTO core.role_permission (role_code, permission_code)
        VALUES
            ('SYS_ADMIN', 'sales.record'),
            ('OPS_MANAGER', 'sales.record'),
            ('STORE_HEAD', 'sales.record'),
            ('STORE_TEAM', 'sales.record')
        ON CONFLICT DO NOTHING;

        CREATE TABLE core.sold_out_event (
            business_date DATE NOT NULL,
            location_code VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
            item_code VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (business_date, location_code, item_code)
        );

        CREATE INDEX idx_sold_out_lookup
            ON core.sold_out_event (location_code, item_code, business_date DESC);

        ALTER TABLE core.sold_out_event ENABLE ROW LEVEL SECURITY;
        ALTER TABLE core.sold_out_event FORCE ROW LEVEL SECURITY;

        CREATE POLICY scope_by_location ON core.sold_out_event
            FOR SELECT
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );

        CREATE POLICY scope_by_location_insert ON core.sold_out_event
            FOR INSERT
            WITH CHECK (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );
        -- No explicit GRANT needed: migration 0004's ALTER DEFAULT PRIVILEGES
        -- IN SCHEMA core already covers every table created after it by the
        -- same owning role, including this one.
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE core.sold_out_event;

        DELETE FROM core.role_permission WHERE permission_code = 'sales.record';
        DELETE FROM core.permission WHERE permission_code = 'sales.record';
    """)
