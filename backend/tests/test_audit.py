"""GET /api/v1/audit, /api/v1/audit/tables, /api/v1/audit/export —
app/api/v1/audit.py. Exercised end to end: create a real audited row
(a location) through its own endpoint, then confirm the audit trail
picks it up — audit.record_change has no RLS of its own (see
app/models/audit.py), so these tests focus on the permission gate, the
date-range filter, and the export shape rather than branch scoping.
"""
import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection

from tests.conftest import login_as_role

TEST_LOCATION_CODE = "PYTAUDIT1"


def _create_location(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "location_code": TEST_LOCATION_CODE,
            "location_type": "BRANCH",
            "location_name": "Pytest Audit Branch",
        },
    )
    assert response.status_code == 201, response.text


def test_requires_audit_read_permission(client: TestClient, db_connection: Connection) -> None:
    # STORE_TEAM holds neither location.create nor audit.read.
    headers = login_as_role(db_connection, "STORE_TEAM")
    response = client.get(
        "/api/v1/audit",
        headers=headers,
        params={"start_date": "2020-01-01", "end_date": "2020-01-02"},
    )
    assert response.status_code == 403, response.text


def test_a_real_mutation_shows_up_in_the_audit_trail(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "SYS_ADMIN")
    _create_location(client, headers)

    today = dt.date.today()
    response = client.get(
        "/api/v1/audit",
        headers=headers,
        params={"start_date": str(today), "end_date": str(today), "table_name": "location"},
    )
    assert response.status_code == 200, response.text
    records = response.json()["items"]
    match = next((r for r in records if r["record_pk"] == TEST_LOCATION_CODE), None)
    assert match is not None, "the location just created should appear in today's audit trail"
    assert match["action"] == "INSERT"
    assert match["table_name"] == "location"
    assert match["changed_by_email"] is not None


def test_date_range_excludes_records_outside_it(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "SYS_ADMIN")
    _create_location(client, headers)

    past = dt.date.today() - dt.timedelta(days=30)
    response = client.get(
        "/api/v1/audit",
        headers=headers,
        params={"start_date": str(past - dt.timedelta(days=2)), "end_date": str(past)},
    )
    assert response.status_code == 200, response.text
    assert all(r["record_pk"] != TEST_LOCATION_CODE for r in response.json()["items"])


def test_list_audited_tables_includes_known_tables(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "SYS_ADMIN")
    _create_location(client, headers)

    response = client.get("/api/v1/audit/tables", headers=headers)
    assert response.status_code == 200, response.text
    assert "location" in response.json()


def test_export_returns_csv(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "SYS_ADMIN")
    _create_location(client, headers)

    today = dt.date.today()
    response = client.get(
        "/api/v1/audit/export",
        headers=headers,
        params={"start_date": str(today), "end_date": str(today)},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    body = response.text
    assert "occurred_at" in body.splitlines()[0]  # header row
    assert TEST_LOCATION_CODE in body
