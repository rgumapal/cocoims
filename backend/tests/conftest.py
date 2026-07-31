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
import uuid
from collections.abc import Generator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, resolve_effective_scope
from app.core.config import settings
from app.core.db import RequestContext, apply_session_context
from app.main import app
from app.models import AppUser

_engine = create_engine(settings.app_database_url)

DEV_PASSWORD = "cocopan-dev-2026"  # set by scripts/set_dev_passwords.py — must have been run


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

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(client: TestClient, email: str, password: str = DEV_PASSWORD) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
