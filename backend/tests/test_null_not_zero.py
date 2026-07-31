"""CLAUDE.md DATA: "Never coerce NULL to 0 in fact tables. Blank, zero and
'not counted' are three different facts." Exercised end-to-end through the
real API (app.api.v1.counts), not just at the DB layer — this is the rule
CLAUDE.md calls "the single most important data rule in the system", so it
gets the full round-trip, not a shortcut.
"""
from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def _open_session(client: TestClient, headers: dict[str, str], count_type: str) -> int:
    response = client.post(
        "/api/v1/counts",
        headers=headers,
        json={"location_code": "KLN", "count_type": count_type, "business_date": "2026-07-31"},
    )
    assert response.status_code == 201, response.text
    return response.json()["count_id"]  # type: ignore[no-any-return]


def test_counted_zero_is_distinct_from_not_counted(client: TestClient) -> None:
    headers = auth_headers(client, "it.admin@cocopan.ph")
    count_id = _open_session(client, headers, "CYCLE")

    response = client.post(
        f"/api/v1/counts/{count_id}/lines",
        headers=headers,
        json=[
            {"item_code": "CP001", "counted_qty": "0", "was_counted": True},
            {"item_code": "CP004", "counted_qty": None, "was_counted": False},
        ],
    )
    assert response.status_code == 200, response.text
    lines = {line["item_code"]: line for line in response.json()}

    zero_count = lines["CP001"]
    skipped = lines["CP004"]

    assert zero_count["was_counted"] is True
    assert zero_count["counted_qty"] == "0.000"

    assert skipped["was_counted"] is False
    assert skipped["counted_qty"] is None

    # The two states must not collapse into the same variance either — a
    # counted zero produces a real, computed variance; a skip has none to
    # compute (counted_qty is NULL, and NULL - anything is NULL in SQL,
    # which is the correct behavior here, not a bug to paper over).
    assert zero_count["variance_qty"] is not None
    assert skipped["variance_qty"] is None


def test_was_counted_survives_a_resubmit(client: TestClient) -> None:
    """Submitting a line again (the upsert path in submit_count_lines)
    must not silently flip was_counted based on whatever counted_qty
    happens to be — the two fields are independent inputs, not derived
    from each other."""
    headers = auth_headers(client, "it.admin@cocopan.ph")
    count_id = _open_session(client, headers, "DAILY_EI")

    client.post(
        f"/api/v1/counts/{count_id}/lines",
        headers=headers,
        json=[{"item_code": "CP001", "counted_qty": None, "was_counted": False}],
    )
    response = client.post(
        f"/api/v1/counts/{count_id}/lines",
        headers=headers,
        json=[{"item_code": "CP001", "counted_qty": "0", "was_counted": True}],
    )
    assert response.status_code == 200, response.text
    line = response.json()[0]
    assert line["was_counted"] is True
    assert line["counted_qty"] == "0.000"
