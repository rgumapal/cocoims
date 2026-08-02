"""Test fixtures.

Runs against the real dev database (cocoims_app role), not mocks — the
properties this suite verifies (RLS, the immutability trigger, generated
columns) are Postgres behavior that a mock cannot reproduce, and this repo
already treats that as untestable any other way (see CLAUDE.md's own
"Local development database" section).

Isolation: one connection + one outer transaction per test, with
get_db overridden to bind to a SAVEPOINT-per-request session on that same
connection (SQLAlchemy's join_transaction_mode="create_savepoint") — so a
route's internal session.commit() releases a savepoint rather than the
outer transaction, and rolling back that outer transaction at teardown
undoes everything the test wrote through the API, however many requests it
made.
"""
import datetime as dt
import uuid
from collections.abc import Generator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, resolve_effective_scope
from app.auth.security import create_token
from app.core.config import settings
from app.core.db import RequestContext, apply_session_context, get_raw_session
from app.main import app
from app.models import AppUser

_engine = create_engine(settings.app_database_url)

DEV_PASSWORD = "cocopan-dev-2026"  # set by scripts/set_dev_passwords.py — must have been run

# A business_date no real Cocopan activity will ever use (the chain was
# founded 2022) — every test that seeds its own stock_movement/count_session
# row and then asserts a row *count* filters on this, so the assertion is
# immune to whatever real or sample-generator data already exists in the
# shared Cloud SQL database (see CLAUDE.md's "Local development database":
# local dev is Cloud SQL directly, not an empty per-test database). Without
# this, a test asserting "exactly 1 row" silently breaks the moment anyone
# runs scripts/seed_sample_data.py against the same branch code.
TEST_SENTINEL_DATE = dt.date(1900, 1, 1)


@pytest.fixture()
def db_connection() -> Generator[Connection, None, None]:
    connection = _engine.connect()
    outer_transaction = connection.begin()
    try:
        yield connection
    finally:
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_connection: Connection) -> Generator[TestClient, None, None]:
    def _get_db_override(
        user: AppUser = Depends(get_current_user),
    ) -> Generator[Session, None, None]:
        session = Session(bind=db_connection, join_transaction_mode="create_savepoint")
        try:
            unrestricted, location_scope = resolve_effective_scope(session, user.user_id)
            apply_session_context(
                session,
                RequestContext(
                    user_id=user.user_id,
                    user_email=user.email,
                    request_id=uuid.uuid4(),
                    location_scope=location_scope,
                    unrestricted=unrestricted,
                ),
            )
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # get_raw_session (auth: login/firebase/me/refresh, and get_current_user's
    # own user lookup on every subsequent request) previously used the real
    # connection pool, not this test's isolated db_connection — meaning a
    # user created inside a test's own transaction was invisible to login,
    # forcing every auth-dependent test to depend on a real, pre-committed
    # seeded account. Overriding it the same way as get_db closes that gap:
    # see login_as_role below, which relies on this.
    def _get_raw_session_override() -> Generator[Session, None, None]:
        session = Session(bind=db_connection, join_transaction_mode="create_savepoint")
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_raw_session] = _get_raw_session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(client: TestClient, email: str, password: str = DEV_PASSWORD) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login_as_role(db_connection: Connection, role_code: str, *, unrestricted: bool = True) -> dict[str, str]:
    """Creates a throwaway user holding exactly one role, inside this
    test's own transaction (rolled back at teardown by db_connection, same
    as everything else the test writes — see this module's docstring), and
    mints a valid access token for them directly.

    Deliberately skips /api/v1/auth/login (bcrypt) and Firebase entirely:
    what these tests verify is permission/role enforcement, not which
    identity provider issued the token, and a real login round-trip can't
    be faked here without either a password on a real seeded account (the
    original design — see git history, e.g. om.north@/cx.lead@/it.admin@
    cocopan.ph, all removed by migration 0012's placeholder cleanup) or
    mocking Google's Firebase token verification. A user created fresh per
    test and torn down by rollback needs neither, and can't go stale the
    way a hardcoded seeded email can.

    unrestricted=True by default (a 'ALL'-scope_type grant, same as
    resolve_effective_scope's own SYS_ADMIN-style shortcut — see that
    function) because most callers are testing *permission* denial, where
    branch scope never enters into it; that's what test_rls_bypass.py's
    raw-SQL tests exist to cover on their own. Pass False for a test that
    specifically cares about scope with no branches granted.
    """
    user_id = db_connection.execute(
        text(
            "INSERT INTO core.app_user (email, full_name, is_active) "
            "VALUES (:email, :name, true) RETURNING user_id"
        ),
        {"email": f"pytest-{role_code.lower()}@test.invalid", "name": f"pytest {role_code}"},
    ).scalar_one()
    db_connection.execute(
        text("INSERT INTO core.user_role (user_id, role_code) VALUES (:uid, :role)"),
        {"uid": user_id, "role": role_code},
    )
    if unrestricted:
        db_connection.execute(
            text("INSERT INTO core.user_scope (user_id, scope_type, scope_value) VALUES (:uid, 'ALL', '*')"),
            {"uid": user_id},
        )
    token = create_token(user_id, "access", dt.timedelta(minutes=5))
    return {"Authorization": f"Bearer {token}"}
