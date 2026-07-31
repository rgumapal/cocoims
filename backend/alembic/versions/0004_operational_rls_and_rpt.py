"""operational RLS fixes + rpt/perf catch-up

Three enforcement gaps surfaced while building the data-entry API.

1. **The app's own DB role is a superuser, which unconditionally bypasses
   RLS.** `cocoims` — the role the app has connected as since the container
   was first created — is the Postgres image's POSTGRES_USER bootstrap role,
   which the official `postgres` image always creates as a superuser.
   Superusers bypass row-level security entirely, and FORCE ROW LEVEL
   SECURITY explicitly does not override that (it only affects the table
   *owner*, and only when the owner isn't also a superuser). Verified live:
   with policies + FORCE already in place, an INSERT for an out-of-scope
   location still succeeded when connected as `cocoims`. FORCE ROW LEVEL
   SECURITY alone is therefore not a fix here — a separate, unprivileged
   login role is required. This migration creates `cocoims_app`
   (NOSUPERUSER, NOBYPASSRLS — the default for a plain role, made explicit)
   with DML grants on `core`/`rpt` and read-only on `audit`, and the backend
   switches its runtime connection to it (`app.core.config.Settings.
   app_database_url`) while Alembic keeps connecting as the owning role,
   since migrations need DDL rights this role deliberately lacks.

2. RLS on core.stock_movement (0001) only has a FOR SELECT policy and no
   FORCE flag. SPEC §7.2 rule 3 requires scope on reads *and* writes; AC-3
   requires this verified "with the API bypassed", which is only meaningful
   once (1) above makes RLS bind at all. Fixed with an INSERT policy plus
   FORCE on stock_movement, and the same SELECT+INSERT+UPDATE+FORCE pattern
   extended to core.count_session (counts are in this phase) and
   core.order_line (not exercised until the ladder phase, but the same
   migration is the cheap place to add it).

3. "core.stock_movement is append-only. No UPDATE or DELETE." (CLAUDE.md
   DATA) was asserted in a comment but never enforced — no REVOKE, no
   trigger. A REVOKE naming `cocoims` wouldn't have worked either
   (ownership confers full privileges regardless of REVOKE); now that
   cocoims_app is a distinct, non-owning role, REVOKE is meaningful for it
   and is applied below. A BEFORE-trigger backs it up regardless of which
   role connects — including future superuser/admin access — and Postgres
   propagates a trigger on a partitioned table to every partition
   automatically, present and future.

Also lands db/ddl/002_rpt.sql (rpt.agg_location_item_dow, mv_daily_network)
and db/perf/001_indexes.sql (SPEC §6.2-6.4), drafted in an earlier pass but
not yet migrated, and enables pg_stat_statements (CLAUDE.md PERFORMANCE;
requires shared_preload_libraries, added to docker-compose.yml's `command`
in this same change since the extension cannot self-load).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-31
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REPO_ROOT = Path(__file__).resolve().parents[3]
RPT_SQL = REPO_ROOT / "db" / "ddl" / "002_rpt.sql"
PERF_SQL = REPO_ROOT / "db" / "perf" / "001_indexes.sql"

# Parsed from settings.app_database_url rather than read separately from the
# environment, so there is exactly one source of truth for the app role's
# credentials — the same .env pydantic-settings already loads for the
# running API (app/core/config.py) — instead of a second, easy-to-forget
# path that would silently drift from it.
_app_url = make_url(settings.app_database_url)
APP_DB_USER = _app_url.username
APP_DB_PASSWORD = _app_url.password

# Shared by every location-scoped policy below (SPEC §7.2's scope_by_location
# example, applied consistently to every table that carries location_code).
_SCOPE_PREDICATE = """
    current_setting('app.unrestricted', true) = 'on'
    OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
"""


def _scoped_rw_policies(table: str) -> str:
    """SELECT + INSERT + UPDATE policies plus FORCE, for a table with a
    direct location_code column. Excludes DELETE deliberately: nothing in
    this phase deletes scoped rows, and adding an unused DELETE policy would
    claim a guarantee no test exercises."""
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;

        CREATE POLICY scope_by_location ON {table}
            FOR SELECT USING ({_SCOPE_PREDICATE});

        CREATE POLICY scope_by_location_insert ON {table}
            FOR INSERT WITH CHECK ({_SCOPE_PREDICATE});

        CREATE POLICY scope_by_location_update ON {table}
            FOR UPDATE USING ({_SCOPE_PREDICATE}) WITH CHECK ({_SCOPE_PREDICATE});

        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
    """


def upgrade() -> None:
    # exec_driver_sql via a raw cursor, not op.execute(): same reasoning as
    # 0001 — these files may contain literal `%` / `:word` tokens that
    # op.execute()'s implicit text() wrapping or psycopg2's own pyformat
    # substitution would misinterpret. A direct cursor call sends the SQL
    # untouched.
    cursor = op.get_bind().connection.cursor()
    cursor.execute(RPT_SQL.read_text(encoding="utf-8"))
    cursor.execute(PERF_SQL.read_text(encoding="utf-8"))
    cursor.close()

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")

    # --- Gap 1: an unprivileged login role, so RLS can bind at all --------
    # Role creation needs a real password bound as a query parameter (never
    # string-interpolated into DDL), so this uses psycopg2's sql.SQL/
    # Identifier composition directly on the raw connection rather than
    # op.execute()'s text() wrapping, which has no parameter-binding story
    # for DDL statements like CREATE ROLE.
    conn = op.get_bind().connection
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_DB_USER,))
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s NOSUPERUSER NOBYPASSRLS").format(
                sql.Identifier(APP_DB_USER)
            ),
            (APP_DB_PASSWORD,),
        )
    else:
        # Idempotent re-run (e.g. downgrade/upgrade during development):
        # keep the password in sync with the current environment rather
        # than silently keeping a stale one.
        cur.execute(
            sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(APP_DB_USER)),
            (APP_DB_PASSWORD,),
        )
    cur.close()

    op.execute(f"""
        GRANT USAGE ON SCHEMA core, rpt, audit TO {APP_DB_USER};

        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO {APP_DB_USER};
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO {APP_DB_USER};
        GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO {APP_DB_USER};

        -- Audit trail is read-only to the app role by design: writes only
        -- happen via audit.fn_capture(), which runs SECURITY DEFINER as the
        -- owning role, so the app never needs (and never gets) direct
        -- INSERT on audit.record_change / audit.access_log.
        GRANT SELECT ON ALL TABLES IN SCHEMA audit TO {APP_DB_USER};

        -- Future tables created by migrations (still run as the owning
        -- role) get the same grants automatically, so this doesn't need
        -- repeating in every subsequent migration.
        ALTER DEFAULT PRIVILEGES IN SCHEMA core
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA core
            GRANT USAGE, SELECT ON SEQUENCES TO {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA rpt
            GRANT SELECT ON TABLES TO {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA audit
            GRANT SELECT ON TABLES TO {APP_DB_USER};

        -- Ledger immutability at the privilege layer too, in addition to
        -- the trigger below: cocoims_app cannot UPDATE/DELETE stock_movement
        -- even before the trigger fires, because the grant itself is absent.
        REVOKE UPDATE, DELETE ON core.stock_movement FROM {APP_DB_USER};
    """)

    # --- Gap 2: RLS write-scope + FORCE ------------------------------------
    op.execute(f"""
        CREATE POLICY scope_by_location_insert ON core.stock_movement
            FOR INSERT WITH CHECK ({_SCOPE_PREDICATE});

        ALTER TABLE core.stock_movement FORCE ROW LEVEL SECURITY;
    """)
    op.execute(_scoped_rw_policies("core.count_session"))
    op.execute(_scoped_rw_policies("core.order_line"))

    # --- Gap 3: ledger immutability, enforced regardless of connecting role
    op.execute("""
        CREATE OR REPLACE FUNCTION core.fn_block_movement_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'core.stock_movement is append-only: % is not permitted. '
                'Use an offsetting movement with reason_code = ''CORRECTION'' instead.',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_stock_movement_immutable
            BEFORE UPDATE OR DELETE ON core.stock_movement
            FOR EACH ROW EXECUTE FUNCTION core.fn_block_movement_mutation();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_stock_movement_immutable ON core.stock_movement;
        DROP FUNCTION IF EXISTS core.fn_block_movement_mutation();
    """)

    for table in ("core.order_line", "core.count_session"):
        op.execute(f"""
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS scope_by_location_update ON {table};
            DROP POLICY IF EXISTS scope_by_location_insert ON {table};
            DROP POLICY IF EXISTS scope_by_location ON {table};
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)

    op.execute("""
        ALTER TABLE core.stock_movement NO FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS scope_by_location_insert ON core.stock_movement;
    """)

    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements;")

    op.execute("""
        DROP INDEX IF EXISTS core.idx_item_price_lookup;
        DROP INDEX IF EXISTS core.idx_movement_lookup;
        DROP INDEX IF EXISTS core.idx_movement_brin;
        DROP INDEX IF EXISTS core.idx_ol_needs_review;
        DROP INDEX IF EXISTS core.idx_ol_grid;
    """)

    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS rpt.mv_daily_network;
        DROP TABLE IF EXISTS rpt.agg_location_item_dow;
    """)

    op.execute(f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA audit REVOKE SELECT ON TABLES FROM {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA rpt REVOKE SELECT ON TABLES FROM {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA core REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_DB_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA core REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_DB_USER};

        REVOKE ALL ON ALL TABLES IN SCHEMA audit FROM {APP_DB_USER};
        REVOKE ALL ON ALL TABLES IN SCHEMA rpt FROM {APP_DB_USER};
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA core FROM {APP_DB_USER};
        REVOKE ALL ON ALL TABLES IN SCHEMA core FROM {APP_DB_USER};
        REVOKE USAGE ON SCHEMA core, rpt, audit FROM {APP_DB_USER};
    """)
    op.execute(f"DROP ROLE IF EXISTS {APP_DB_USER};")
