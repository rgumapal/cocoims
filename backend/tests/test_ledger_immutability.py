"""CLAUDE.md DATA: "core.stock_movement is append-only. No UPDATE or
DELETE. Corrections are offsetting movements."

Two layers, both tested (migration 0004): a grant-level REVOKE for
cocoims_app, and a BEFORE UPDATE/DELETE trigger that blocks every role —
including cocoims, the owning superuser, for whom a REVOKE alone would
have no effect (ownership always confers full privileges).
"""
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.core.config import settings

_app_engine = create_engine(settings.app_database_url)
_owner_engine = create_engine(settings.database_url)


def _seed_row(conn: Connection) -> None:
    conn.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    conn.execute(
        text(
            "INSERT INTO core.stock_movement "
            "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
            "VALUES ('2026-07-31', 'CMSY-01', 'CP001', 'OPENING', 1, 'pc', 'MANUAL_UPLOAD')"
        )
    )


@pytest.fixture()
def app_role_conn() -> Generator[Connection, None, None]:
    conn = _app_engine.connect()
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()


@pytest.fixture()
def owner_conn() -> Generator[Connection, None, None]:
    """cocoims: the owning superuser. Used only to prove the trigger, not
    the grant, is what stops this role — REVOKE cannot bind an owner."""
    conn = _owner_engine.connect()
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()


def test_app_role_cannot_update(app_role_conn: Connection) -> None:
    _seed_row(app_role_conn)
    with pytest.raises(DBAPIError, match="permission denied"):
        app_role_conn.execute(text("UPDATE core.stock_movement SET qty = 99 WHERE item_code = 'CP001'"))


def test_app_role_cannot_delete(app_role_conn: Connection) -> None:
    _seed_row(app_role_conn)
    with pytest.raises(DBAPIError, match="permission denied"):
        app_role_conn.execute(text("DELETE FROM core.stock_movement WHERE item_code = 'CP001'"))


def test_owning_superuser_still_cannot_update(owner_conn: Connection) -> None:
    """The grant-level REVOKE only applies to cocoims_app — cocoims owns
    the table and privileges can't be revoked from an owner. The trigger is
    what has to stop this role, and this is the test that proves it does.
    """
    _seed_row(owner_conn)
    with pytest.raises(DBAPIError, match="append-only"):
        owner_conn.execute(text("UPDATE core.stock_movement SET qty = 99 WHERE item_code = 'CP001'"))


def test_owning_superuser_still_cannot_delete(owner_conn: Connection) -> None:
    _seed_row(owner_conn)
    with pytest.raises(DBAPIError, match="append-only"):
        owner_conn.execute(text("DELETE FROM core.stock_movement WHERE item_code = 'CP001'"))
