"""Database engine and session plumbing for the unprivileged app role.

Two connections exist in this codebase, deliberately kept separate — see
alembic/versions/0004_operational_rls_and_rpt.py for why:

- settings.database_url (the owning/superuser role) is used ONLY by Alembic
  and admin scripts. It bypasses RLS unconditionally and must never back a
  request handler.
- settings.app_database_url (cocoims_app: NOSUPERUSER, NOBYPASSRLS) is what
  every request in this application uses. RLS policies only bind against it.

get_raw_session() gives a plain session with no request context set — only
safe for tables without row-level security (app_user, role, permission,
user_scope carry no RLS policy), which is exactly what authentication itself
needs before a user is even known. Anything touching a scoped table
(stock_movement, count_session, order_line) must go through
app.auth.deps.get_db instead, which calls apply_session_context() below
before yielding — that composition lives in app.auth.deps rather than here
because it needs the authenticated user (app.auth.deps.get_current_user) to
resolve scope, and this module must not import from app.auth (that would
make app.auth's own import of get_raw_session from here circular).
"""
from collections.abc import Generator
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.app_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_raw_session() -> Generator[Session, None, None]:
    """FastAPI dependency: a session with no SET LOCAL context.

    Only safe for tables without row-level security. Used by authentication
    itself before a user is known, and is not a substitute for get_db on any
    endpoint that reads or writes a scoped table.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class RequestContext(NamedTuple):
    user_id: int
    user_email: str
    request_id: UUID
    location_scope: list[str]
    unrestricted: bool


def apply_session_context(session: Session, ctx: RequestContext) -> None:
    """Binds app.user_id / app.user_email / app.request_id / app.location_scope
    / app.unrestricted to the current transaction, which is what:

    - audit.fn_capture() reads to stamp changed_by / changed_by_email /
      request_id on every audited row (SPEC §4.9) — "a write without session
      context is a bug" (CLAUDE.md ACCESS), and this is what makes that true
      rather than aspirational, since nothing downstream can proceed without
      it having been called first.
    - the RLS policies on stock_movement / count_session / order_line read
      to decide which rows are visible/writable (migration 0004).

    Uses set_config(), not a raw `SET LOCAL ... = :param` string: Postgres's
    SET command is a utility statement whose value is a literal in the
    grammar, not a bind parameter — passing one through text(":v") would not
    do what it looks like it does. set_config() is a normal function call
    and takes real, safely-bound arguments. The `true` third argument is
    is_local: scoped to this transaction only, exactly matching SET LOCAL's
    lifetime (cleared at the next COMMIT/ROLLBACK) rather than the
    connection's lifetime, which matters because connections are pooled and
    reused across unrelated requests.
    """
    session.execute(
        text("SELECT set_config('app.user_id', :v, true)"), {"v": str(ctx.user_id)}
    )
    session.execute(
        text("SELECT set_config('app.user_email', :v, true)"), {"v": ctx.user_email}
    )
    session.execute(
        text("SELECT set_config('app.request_id', :v, true)"), {"v": str(ctx.request_id)}
    )
    session.execute(
        text("SELECT set_config('app.location_scope', :v, true)"),
        {"v": ",".join(ctx.location_scope)},
    )
    session.execute(
        text("SELECT set_config('app.unrestricted', :v, true)"),
        {"v": "on" if ctx.unrestricted else "off"},
    )
