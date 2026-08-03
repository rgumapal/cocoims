"""GET /api/v1/waste (already-reported visibility) and the reverse
correction — app/api/v1/waste.py.
"""
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection

from tests.conftest import TEST_SENTINEL_DATE, login_as_role

LOCATION = "KLN"
ITEM = "CP001"


def _record(client: TestClient, headers: dict[str, str], qty: str = "5", reason: str = "UNSOLD") -> dict:
    response = client.post(
        "/api/v1/waste",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "location_code": LOCATION,
            "item_code": ITEM,
            "qty": qty,
            "reason_code": reason,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _list(client: TestClient, headers: dict[str, str]) -> list[dict]:
    response = client.get(
        "/api/v1/waste",
        headers=headers,
        params={"location_code": LOCATION, "item_code": ITEM, "business_date": str(TEST_SENTINEL_DATE)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_list_is_empty_before_anything_is_logged(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    assert _list(client, headers) == []


def test_logged_entry_appears_in_the_list(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    movement = _record(client, headers, qty="6")

    entries = _list(client, headers)
    assert len(entries) == 1
    assert entries[0]["qty"] == "6.000"
    assert entries[0]["reason_code"] == "UNSOLD"
    assert entries[0]["is_reversed"] is False
    assert entries[0]["movement_id"] == movement["movement_id"]


def test_two_entries_same_day_both_appear(client: TestClient, db_connection: Connection) -> None:
    """Multiple waste entries for the same (branch, item, date) are
    legitimate — a spoiled batch and a separately damaged one — not
    collapsed into one net figure the way receiving's GET is."""
    headers = login_as_role(db_connection, "STORE_HEAD")
    _record(client, headers, qty="3", reason="UNSOLD")
    _record(client, headers, qty="2", reason="DAMAGED_IN_TRANSIT")

    entries = _list(client, headers)
    assert len(entries) == 2
    assert {e["reason_code"] for e in entries} == {"UNSOLD", "DAMAGED_IN_TRANSIT"}


def test_list_without_item_code_returns_the_whole_days_waste_for_the_branch(
    client: TestClient, db_connection: Connection
) -> None:
    """The main Waste Log screen shows one table per branch/date across
    every item, not a per-item lookup — item_code narrows the query, it
    isn't required."""
    headers = login_as_role(db_connection, "STORE_HEAD")
    _record(client, headers, qty="3", reason="UNSOLD")  # ITEM = CP001
    response = client.post(
        "/api/v1/waste",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "location_code": LOCATION,
            "item_code": "CP008",
            "qty": "4",
            "reason_code": "EXPIRED",
        },
    )
    assert response.status_code == 201, response.text

    whole_day = client.get(
        "/api/v1/waste",
        headers=headers,
        params={"location_code": LOCATION, "business_date": str(TEST_SENTINEL_DATE)},
    )
    assert whole_day.status_code == 200, whole_day.text
    assert {e["item_code"] for e in whole_day.json()} == {"CP001", "CP008"}

    narrowed = _list(client, headers)  # item_code=CP001 only
    assert {e["item_code"] for e in narrowed} == {"CP001"}


def test_reverse_marks_entry_as_reversed_and_zeroes_its_effect(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    movement = _record(client, headers, qty="4")

    reverse = client.post(f"/api/v1/waste/{movement['movement_id']}/reverse", headers=headers)
    assert reverse.status_code == 201, reverse.text
    assert reverse.json()["qty"] == "4.000"  # positive: undoes the -4 original
    assert reverse.json()["reason_code"] == "CORRECTION"

    entries = _list(client, headers)
    original = next(e for e in entries if e["movement_id"] == movement["movement_id"])
    assert original["is_reversed"] is True


def test_reverse_twice_is_rejected(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    movement = _record(client, headers, qty="4")
    client.post(f"/api/v1/waste/{movement['movement_id']}/reverse", headers=headers).raise_for_status()

    second = client.post(f"/api/v1/waste/{movement['movement_id']}/reverse", headers=headers)
    assert second.status_code == 409, second.text


def test_reverse_unknown_movement_is_404(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    response = client.post("/api/v1/waste/999999999/reverse", headers=headers)
    assert response.status_code == 404, response.text


def test_reverse_is_not_restricted_to_the_original_creator(
    client: TestClient, db_connection: Connection
) -> None:
    """Deliberate: waste.record is the only gate, same as every other
    permission in this app — a different user holding it can correct
    someone else's mis-entry (see reverse_waste's own docstring)."""
    creator = login_as_role(db_connection, "STORE_TEAM")
    movement = _record(client, creator, qty="4")

    corrector = login_as_role(db_connection, "STORE_HEAD")
    response = client.post(f"/api/v1/waste/{movement['movement_id']}/reverse", headers=corrector)
    assert response.status_code == 201, response.text
