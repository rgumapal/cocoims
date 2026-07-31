"""baseline schema + seed

Reproduces db/ddl/001_schema.sql and db/seed/001_seed.sql via Alembic, so
`alembic upgrade head` builds an identical database on any environment (CI,
a teammate's machine, Cloud SQL) to what docker-entrypoint-initdb.d applies
to the local cocoims-db container. The dev container is stamped rather than
re-run, since it already applied the same files on first boot.

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_SQL = REPO_ROOT / "db" / "ddl" / "001_schema.sql"
SEED_SQL = REPO_ROOT / "db" / "seed" / "001_seed.sql"

ENUM_TYPES = [
    "item_type", "packaging_type", "item_status", "location_type", "store_format",
    "location_status", "replen_policy", "movement_type", "order_status",
    "excess_source", "audit_action",
]


def _strip_outer_transaction(sql: str) -> str:
    # db/ddl and db/seed files wrap themselves in BEGIN;/COMMIT; so they can
    # also be run standalone via psql. Alembic already runs each migration in
    # its own transaction, so the outer BEGIN/COMMIT is stripped here rather
    # than nested — a raw COMMIT inside op.execute would end Alembic's
    # transaction early and leave its own bookkeeping out of sync.
    lines = [line for line in sql.splitlines() if line.strip() not in ("BEGIN;", "COMMIT;")]
    return "\n".join(lines)


def upgrade() -> None:
    # exec_driver_sql, not op.execute(): op.execute() wraps the string in
    # sqlalchemy.text(), which scans for `:name` bind-parameter placeholders
    # and misfires on things like the `:true` inside a JSONB example in a SQL
    # comment (db/ddl/001_schema.sql, ref_week_flags). exec_driver_sql sends
    # the SQL straight to the DBAPI with no placeholder parsing.
    # Drop one level below exec_driver_sql too: the SQL contains literal `%s`
    # / `%L` tokens (arguments to Postgres's format() in the partition-
    # creation DO blocks) that psycopg2 tries to treat as its own pyformat
    # placeholders the moment *any* parameters value — even () — is passed
    # alongside the statement. Calling the DBAPI cursor directly with a
    # single argument disables psycopg2's substitution entirely, while still
    # running on the same connection/transaction Alembic is managing.
    cursor = op.get_bind().connection.cursor()
    cursor.execute(_strip_outer_transaction(SCHEMA_SQL.read_text(encoding="utf-8")))
    cursor.execute(_strip_outer_transaction(SEED_SQL.read_text(encoding="utf-8")))
    cursor.close()


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS stg CASCADE")
    op.execute("DROP SCHEMA IF EXISTS rpt CASCADE")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
