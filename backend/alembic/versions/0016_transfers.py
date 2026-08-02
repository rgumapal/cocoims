"""Transfers v1 (branch-to-branch rebalance) — docs/features/TRANSFERS_V1.md

Phase 0 (this migration's design notes) confirmed the ledger already had
everything transfers need: `movement_type` already has TRANSFER_OUT/
TRANSFER_IN (db/ddl/001_schema.sql §4.1) and `location_type` already has
IN_TRANSIT — both schema-only until now, never exercised (zero
TRANSFER_IN/OUT rows existed before this migration). Only three things were
actually missing, all added here:

1. **core.transfer / core.transfer_line** — the two new tables. `transfer`
   gets an audit trigger (single BIGSERIAL PK, fits fn_capture's
   single-column-PK contract). `transfer_line` does NOT — same exemption
   already applied to role_permission/uom_conversion/item_location_param
   (composite PK, see 001_schema.sql's comment above the audit triggers
   block); (transfer_id, item_code) is a composite PK here too.

   `transfer_line` denormalises `source_location_code`/`dest_location_code`
   from its parent rather than relying on a join for RLS, deliberately —
   `core.count_line` took the opposite approach (no location column, scope
   enforced only by the app always querying through `count_session` first)
   and that gap is flagged as a real risk in docs/INTEGRITY_ASSESSMENT.md's
   top-5 (#3). Denormalising here is safe because a transfer's source/dest
   are fixed at creation and never edited by any endpoint in this build.

2. **The in-transit location itself.** `core.location` had zero
   `location_type = 'IN_TRANSIT'` rows. Seeded as `TRANSIT` below.

3. **An RLS carve-out for that location on `core.stock_movement`.** The
   brief requires the in-transit location be "in nobody's scope" — but
   every transfer ship/receive posts a real stock_movement row *at* that
   location (source → in-transit, in-transit → destination). Under the
   existing `scope_by_location`/`scope_by_location_insert` policies
   (migration 0004), a normal scoped user (e.g. a Store Team member scoped
   to one branch) would get an RLS violation trying to insert the
   in-transit leg, because TRANSIT is in nobody's `app.location_scope`.
   Fixed by widening those two policies (`ALTER POLICY`, not drop/recreate,
   to preserve policy identity) with `OR location_code = 'TRANSIT'` — a
   fixed, known carve-out for one specific system location, not a scope
   grant, so it doesn't leak any *branch's* data the way a blanket
   unrestricted grant would.

RLS on transfer/transfer_line is coarser than the ship-vs-receive split the
brief describes ("ship requires scope on source, receive requires scope on
destination"): a single UPDATE policy allows a caller to touch the row if
*either* side is in their scope (matching read visibility), and the
precise ship-must-be-source / receive-must-be-dest rule is enforced in
`app.domain.transfer` instead — same split this codebase already uses for
count approval's separation-of-duties (SPEC §7.4, `app/api/v1/counts.py`):
RLS is the coarse branch-boundary backstop, nuanced business rules live in
the service layer. Verified with dedicated tests, not just asserted here.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPE_PREDICATE_EITHER_SIDE = """
    current_setting('app.unrestricted', true) = 'on'
    OR source_location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
    OR dest_location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
"""
_SCOPE_PREDICATE_SOURCE_ONLY = """
    current_setting('app.unrestricted', true) = 'on'
    OR source_location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
"""


def upgrade() -> None:
    op.execute("CREATE TYPE transfer_status AS ENUM ('DRAFT','IN_TRANSIT','RECEIVED','CANCELLED');")

    op.execute("""
        CREATE TABLE core.transfer (
            transfer_id             BIGSERIAL PRIMARY KEY,
            transfer_no             VARCHAR(20) UNIQUE,
            source_location_code    VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
            dest_location_code      VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
            status                  transfer_status NOT NULL DEFAULT 'DRAFT',
            reason_code             VARCHAR(40) REFERENCES core.reason_code(reason_code),
            notes                   TEXT,
            created_by              BIGINT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            shipped_by              BIGINT,
            shipped_at              TIMESTAMPTZ,
            ship_idempotency_key    VARCHAR(120),
            received_by             BIGINT,
            received_at             TIMESTAMPTZ,
            receive_idempotency_key VARCHAR(120),
            cancelled_by            BIGINT,
            cancelled_at            TIMESTAMPTZ,
            CONSTRAINT chk_transfer_source_ne_dest CHECK (source_location_code <> dest_location_code)
        );

        -- transfer_no is set application-side once transfer_id is known
        -- (TRF-000123), not a DB default — see app/domain/transfer.py.

        CREATE INDEX idx_transfer_receive_queue ON core.transfer (dest_location_code)
            WHERE status = 'IN_TRANSIT';
        CREATE INDEX idx_transfer_source_history ON core.transfer (source_location_code, created_at DESC);

        CREATE TABLE core.transfer_line (
            transfer_id             BIGINT NOT NULL REFERENCES core.transfer(transfer_id) ON DELETE CASCADE,
            item_code                VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
            -- Denormalised from the parent transfer at insert time, never
            -- updated after — see this migration's docstring for why.
            source_location_code    VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
            dest_location_code      VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
            qty_requested           NUMERIC(12,3) NOT NULL,
            qty_shipped             NUMERIC(12,3),   -- NULL until ship
            qty_received            NUMERIC(12,3),   -- NULL until receive
            variance_qty            NUMERIC(12,3) GENERATED ALWAYS AS (qty_received - qty_shipped) STORED,
            variance_reason_code    VARCHAR(40) REFERENCES core.reason_code(reason_code),
            PRIMARY KEY (transfer_id, item_code)
        );
    """)

    # --- audit trail: transfer only (composite-PK transfer_line is exempt,
    # same convention as role_permission/uom_conversion/item_location_param)
    op.execute("""
        CREATE TRIGGER trg_audit_transfer AFTER INSERT OR UPDATE OR DELETE ON core.transfer
            FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('transfer_id');
    """)

    # --- RLS: transfer ---------------------------------------------------
    op.execute(f"""
        ALTER TABLE core.transfer ENABLE ROW LEVEL SECURITY;

        CREATE POLICY scope_by_either_location ON core.transfer
            FOR SELECT USING ({_SCOPE_PREDICATE_EITHER_SIDE});

        CREATE POLICY scope_by_source_insert ON core.transfer
            FOR INSERT WITH CHECK ({_SCOPE_PREDICATE_SOURCE_ONLY});

        -- Coarse backstop only — ship-must-be-source / receive-must-be-dest
        -- is enforced in app.domain.transfer. See docstring.
        CREATE POLICY scope_by_either_location_update ON core.transfer
            FOR UPDATE USING ({_SCOPE_PREDICATE_EITHER_SIDE}) WITH CHECK ({_SCOPE_PREDICATE_EITHER_SIDE});

        ALTER TABLE core.transfer FORCE ROW LEVEL SECURITY;
    """)

    # --- RLS: transfer_line ------------------------------------------------
    op.execute(f"""
        ALTER TABLE core.transfer_line ENABLE ROW LEVEL SECURITY;

        CREATE POLICY scope_by_either_location ON core.transfer_line
            FOR SELECT USING ({_SCOPE_PREDICATE_EITHER_SIDE});

        CREATE POLICY scope_by_source_insert ON core.transfer_line
            FOR INSERT WITH CHECK ({_SCOPE_PREDICATE_SOURCE_ONLY});

        CREATE POLICY scope_by_either_location_update ON core.transfer_line
            FOR UPDATE USING ({_SCOPE_PREDICATE_EITHER_SIDE}) WITH CHECK ({_SCOPE_PREDICATE_EITHER_SIDE});

        ALTER TABLE core.transfer_line FORCE ROW LEVEL SECURITY;
    """)

    # --- RLS carve-out: the in-transit leg of every ship/receive posts a
    # stock_movement row at a location that is deliberately in nobody's
    # scope. ALTER POLICY (not drop/recreate) preserves policy identity.
    op.execute("""
        ALTER POLICY scope_by_location ON core.stock_movement
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
                OR location_code = 'TRANSIT'
            );

        ALTER POLICY scope_by_location_insert ON core.stock_movement
            WITH CHECK (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
                OR location_code = 'TRANSIT'
            );
    """)

    # --- the in-transit location itself -----------------------------------
    # status left at its default ('PLANNED') deliberately: is_active/
    # is_orderable are GENERATED off status (CLAUDE.md BRANCHES), and this
    # is neither — it must never be orderable or count toward network KPIs.
    op.execute("""
        INSERT INTO core.location (location_code, location_type, location_name)
        VALUES ('TRANSIT', 'IN_TRANSIT', 'In-Transit (Network)')
        ON CONFLICT DO NOTHING;
    """)

    # --- permissions --------------------------------------------------------
    op.execute("""
        INSERT INTO core.permission (permission_code, resource, action, label, is_destructive) VALUES
            ('transfer.read',    'transfer', 'read',    'View transfers', FALSE),
            ('transfer.create',  'transfer', 'create',  'Create a transfer', FALSE),
            ('transfer.ship',    'transfer', 'ship',    'Ship a transfer', FALSE),
            ('transfer.receive', 'transfer', 'receive', 'Receive a transfer', FALSE),
            ('transfer.cancel',  'transfer', 'cancel',  'Cancel a transfer', TRUE)
        ON CONFLICT DO NOTHING;

        INSERT INTO core.role_permission (role_code, permission_code) VALUES
            ('SYS_ADMIN',      'transfer.read'),
            ('DEMAND_PLANNER', 'transfer.read'),
            ('OPS_MANAGER',    'transfer.read'),
            ('AREA_HEAD',      'transfer.read'),
            ('STORE_HEAD',     'transfer.read'),
            ('STORE_TEAM',     'transfer.read'),

            ('SYS_ADMIN',      'transfer.create'),
            ('DEMAND_PLANNER', 'transfer.create'),
            ('OPS_MANAGER',    'transfer.create'),
            ('AREA_HEAD',      'transfer.create'),
            ('STORE_HEAD',     'transfer.create'),

            ('SYS_ADMIN',      'transfer.ship'),
            ('OPS_MANAGER',    'transfer.ship'),
            ('STORE_HEAD',     'transfer.ship'),
            ('STORE_TEAM',     'transfer.ship'),

            ('SYS_ADMIN',      'transfer.receive'),
            ('OPS_MANAGER',    'transfer.receive'),
            ('STORE_HEAD',     'transfer.receive'),
            ('STORE_TEAM',     'transfer.receive'),

            ('SYS_ADMIN',      'transfer.cancel'),
            ('DEMAND_PLANNER', 'transfer.cancel'),
            ('OPS_MANAGER',    'transfer.cancel'),
            ('AREA_HEAD',      'transfer.cancel'),
            ('STORE_HEAD',     'transfer.cancel')
        ON CONFLICT DO NOTHING;
    """)

    # --- reason codes ---------------------------------------------------
    # CORRECTION and DAMAGED_IN_TRANSIT already exist (categories ADJUSTMENT
    # and WASTE respectively, from db/seed/001_seed.sql and 002_client_data.sql)
    # — reused as-is, ON CONFLICT DO NOTHING so this doesn't collide with
    # them. The five genuinely new ones get their own TRANSFER category;
    # reason_code.category has no CHECK constraint (VARCHAR(20), advisory
    # only per 001_schema.sql's comment), so introducing a new value is safe.
    op.execute("""
        INSERT INTO core.reason_code (reason_code, category, label, requires_note) VALUES
            ('REBALANCE_SOLD_OUT', 'TRANSFER', 'Rebalance — destination sold out', FALSE),
            ('REBALANCE_SURPLUS',  'TRANSFER', 'Rebalance — source has surplus', FALSE),
            ('NEAR_EXPIRY',        'TRANSFER', 'Near expiry — move before it wastes', FALSE),
            ('SHORT_RECEIPT',      'TRANSFER', 'Received less than shipped', TRUE),
            ('OVER_RECEIPT',       'TRANSFER', 'Received more than shipped', TRUE)
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM core.reason_code WHERE reason_code IN
            ('REBALANCE_SOLD_OUT', 'REBALANCE_SURPLUS', 'NEAR_EXPIRY', 'SHORT_RECEIPT', 'OVER_RECEIPT');

        DELETE FROM core.role_permission WHERE permission_code LIKE 'transfer.%';
        DELETE FROM core.permission WHERE permission_code LIKE 'transfer.%';

        DELETE FROM core.location WHERE location_code = 'TRANSIT';
    """)

    op.execute("""
        ALTER POLICY scope_by_location ON core.stock_movement
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );

        ALTER POLICY scope_by_location_insert ON core.stock_movement
            WITH CHECK (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );
    """)

    op.execute("DROP TRIGGER IF EXISTS trg_audit_transfer ON core.transfer;")
    op.execute("DROP TABLE IF EXISTS core.transfer_line;")
    op.execute("DROP TABLE IF EXISTS core.transfer;")
    op.execute("DROP TYPE IF EXISTS transfer_status;")
