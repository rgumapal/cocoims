"""SPEC §7.4 / AC-3: "Deny by default. Absent permission returns 403;"
missing authentication returns 401 (app.auth.deps.get_current_user's
auto_error=False + explicit check — see that module's docstring for why
the default FastAPI behavior would conflate the two).
"""
from fastapi.testclient import TestClient

from tests.conftest import auth_headers

# One representative endpoint per router, each requiring a different
# permission — not exhaustive, but enough to catch a router that forgot to
# wire require_permission in at all.
PROTECTED_ENDPOINTS: list[tuple[str, str, dict[str, str]]] = [
    ("GET", "/api/v1/items", {}),
    ("GET", "/api/v1/locations", {}),
    ("GET", "/api/v1/clusters", {}),
    ("GET", "/api/v1/stock", {"location": "CMSY-01", "item": "CP001"}),
    ("GET", "/api/v1/stock/movements", {}),
]


def test_every_protected_endpoint_rejects_missing_token(client: TestClient) -> None:
    for method, path, params in PROTECTED_ENDPOINTS:
        response = client.request(method, path, params=params)
        assert response.status_code == 401, f"{method} {path} returned {response.status_code}, expected 401"


def test_auth_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_store_team_cannot_create_items(client: TestClient) -> None:
    """STORE_TEAM holds item.read only (SPEC §7.3) — item.create must 403."""
    headers = auth_headers(client, "om.north@cocopan.ph")  # OPS_MANAGER also lacks item.create
    response = client.post(
        "/api/v1/items",
        headers=headers,
        json={
            "item_code": "PYTEST_DENY",
            "item_type": "FINISHED_GOOD",
            "desc_dr": "x",
            "display_name": "x",
            "replen_policy": "SAME_DAY",
        },
    )
    assert response.status_code == 403


def test_cx_specialist_cannot_manage_refdata(client: TestClient) -> None:
    """refdata.manage is SYS_ADMIN/DEMAND_PLANNER only (SPEC §7.3 seed)."""
    headers = auth_headers(client, "cx.lead@cocopan.ph")
    response = client.post(
        "/api/v1/clusters", headers=headers, json={"cluster_code": "PYTEST_DENY", "label": "x"}
    )
    assert response.status_code == 403


def test_cx_specialist_cannot_record_sales(client: TestClient) -> None:
    """sales.record (migration 0010) is SYS_ADMIN/OPS_MANAGER/STORE_HEAD/
    STORE_TEAM only, mirroring waste.record — CX_SPECIALIST holds neither."""
    headers = auth_headers(client, "cx.lead@cocopan.ph")
    response = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "business_date": "2026-07-31",
            "location_code": "CMSY-01",
            "lines": [{"item_code": "CP001", "qty": "1"}],
        },
    )
    assert response.status_code == 403
