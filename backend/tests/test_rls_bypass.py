"""AC-3: "An OM cannot read or write another OM's branches... verified at
the database layer with the API bypassed."

No FastAPI TestClient anywhere in this file — a raw connection as
cocoims_app, GUCs set by hand exactly the way app.core.db.
apply_session_context does it. This is deliberately the same style of test
that caught the original bug in migration 0004 (RLS configured but not
actually binding because the app's role was a superuser) — it exercises
Postgres's enforcement directly, with no application code in the path that
could paper over a gap.
"""
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError

from app.core.config import settings

_app_engine = create_engine(settings.app_database_url)


@pytest.fixture()
def app_role_conn() -> Generator[Connection, None, None]:
    """A raw connection as cocoims_app — never cocoims, which would
    silently bypass RLS as a superuser (see migration 0004's docstring)."""
    conn = _app_engine.connect()
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()


def _set_scope(conn: Connection, *, location_scope: list[str], unrestricted: bool) -> None:
    conn.execute(
        text("SELECT set_config('app.location_scope', :v, true)"),
        {"v": ",".join(location_scope)},
    )
    conn.execute(
        text("SELECT set_config('app.unrestricted', :v, true)"),
        {"v": "on" if unrestricted else "off"},
    )


def _seed_movement(conn: Connection, location_code: str) -> None:
    """Inserted as an unrestricted, in-scope write first so each test's
    scope-restriction assertions run against real pre-existing data, not
    an empty table (an empty result could otherwise mean "correctly scoped"
    or "nothing here at all" — indistinguishable)."""
    _set_scope(conn, location_scope=[location_code], unrestricted=False)
    conn.execute(
        text(
            "INSERT INTO core.stock_movement "
            "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
            "VALUES (:d, :loc, 'CP001', 'OPENING', 1, 'pc', 'MANUAL_UPLOAD')"
        ),
        {"d": "2026-07-31", "loc": location_code},
    )


def test_scoped_read_excludes_other_branches(app_role_conn: Connection) -> None:
    _seed_movement(app_role_conn, "KLN")

    _set_scope(app_role_conn, location_scope=["CMSY-01"], unrestricted=False)
    visible = app_role_conn.execute(
        text("SELECT count(*) FROM core.stock_movement WHERE location_code = 'KLN'")
    ).scalar_one()
    assert visible == 0


def test_scoped_read_includes_own_branch(app_role_conn: Connection) -> None:
    _seed_movement(app_role_conn, "KLN")

    _set_scope(app_role_conn, location_scope=["KLN"], unrestricted=False)
    visible = app_role_conn.execute(
        text("SELECT count(*) FROM core.stock_movement WHERE location_code = 'KLN'")
    ).scalar_one()
    assert visible == 1


def test_scoped_write_to_other_branch_rejected(app_role_conn: Connection) -> None:
    _set_scope(app_role_conn, location_scope=["CMSY-01"], unrestricted=False)
    with pytest.raises(ProgrammingError, match="row-level security"):
        app_role_conn.execute(
            text(
                "INSERT INTO core.stock_movement "
                "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
                "VALUES ('2026-07-31', 'KLN', 'CP001', 'OPENING', 1, 'pc', 'MANUAL_UPLOAD')"
            )
        )


def test_scoped_write_to_own_branch_succeeds(app_role_conn: Connection) -> None:
    _set_scope(app_role_conn, location_scope=["KLN"], unrestricted=False)
    app_role_conn.execute(
        text(
            "INSERT INTO core.stock_movement "
            "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
            "VALUES ('2026-07-31', 'KLN', 'CP001', 'OPENING', 1, 'pc', 'MANUAL_UPLOAD')"
        )
    )  # no exception = pass


def test_unrestricted_scope_sees_every_branch(app_role_conn: Connection) -> None:
    _seed_movement(app_role_conn, "KLN")

    _set_scope(app_role_conn, location_scope=[], unrestricted=True)
    visible = app_role_conn.execute(
        text("SELECT count(*) FROM core.stock_movement WHERE location_code = 'KLN'")
    ).scalar_one()
    assert visible == 1


def test_count_session_is_scoped_the_same_way(app_role_conn: Connection) -> None:
    """count_session carries its own RLS policy (migration 0004) — this
    isn't automatic just because stock_movement has one, so it gets its
    own assertion rather than being assumed from the tests above."""
    _set_scope(app_role_conn, location_scope=["KLN"], unrestricted=False)
    app_role_conn.execute(
        text(
            "INSERT INTO core.count_session (location_code, count_type, business_date, status) "
            "VALUES ('KLN', 'CYCLE', '2026-07-31', 'OPEN')"
        )
    )

    _set_scope(app_role_conn, location_scope=["CMSY-01"], unrestricted=False)
    visible = app_role_conn.execute(
        text("SELECT count(*) FROM core.count_session WHERE location_code = 'KLN'")
    ).scalar_one()
    assert visible == 0

    with pytest.raises(ProgrammingError, match="row-level security"):
        app_role_conn.execute(
            text(
                "INSERT INTO core.count_session (location_code, count_type, business_date, status) "
                "VALUES ('KLN', 'CYCLE', '2026-08-01', 'OPEN')"
            )
        )


def test_order_line_rls_is_configured() -> None:
    """order_line has no write path yet in this phase (forecast/ladder is
    deferred), so there's nothing to round-trip a row through — this
    confirms the policy and FORCE flag from migration 0004 are actually in
    place rather than leaving the table untested until the ladder phase
    reintroduces it.
    """
    with _app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'core.order_line'::regclass"
            )
        ).one()
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True
