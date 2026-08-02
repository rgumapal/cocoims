"""Branch-to-branch transfers — docs/features/TRANSFERS_V1.md, AC-5.

Ship/receive round-trip through the real API, not just domain-level unit
tests: the acceptance criteria are stated in terms of what the API does
to the ledger end-to-end, and app.domain.transfer's functions only take
an already-open session — exercising them directly wouldn't prove
get_db's session-context wiring, RLS, and the permission layer actually
compose the way the routes assume, which is exactly the class of gap
docs/INTEGRITY_ASSESSMENT.md flagged (a missing policy silently no-ops
rather than erroring; a scope check skipped isn't caught by a type
checker). AC-3's "verified at the database layer with the API bypassed"
is covered separately, with a raw connection, same style as
test_rls_bypass.py.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError

from app.auth.security import create_token
from app.core.config import settings
from tests.conftest import TEST_SENTINEL_DATE, login_as_role

SOURCE = "KLN"
DEST = "AGL"
THIRD = "ANO"  # neither source nor dest, for the "not visible to a stranger" case

MULTI_DAY_ITEM = "CP001"  # shelf_life_days=3
SAME_DAY_ITEM = "CP008"  # shelf_life_days=0

_app_engine = create_engine(settings.app_database_url)


def _login_scoped_to(db_connection: Connection, role_code: str, location_code: str) -> dict[str, str]:
    """Same idea as tests.conftest.login_as_role, but grants exactly one
    LOCATION scope instead of ALL/none. Needed here because the ship-
    must-be-source / receive-must-be-destination rule (app.api.v1.
    transfers._require_scope) can only be exercised with a user scoped to
    precisely one side of a transfer."""
    user_id = db_connection.execute(
        text(
            "INSERT INTO core.app_user (email, full_name, is_active) "
            "VALUES (:email, :name, true) RETURNING user_id"
        ),
        {
            "email": f"pytest-{role_code.lower()}-{location_code.lower()}@test.invalid",
            "name": f"pytest {role_code} @ {location_code}",
        },
    ).scalar_one()
    db_connection.execute(
        text("INSERT INTO core.user_role (user_id, role_code) VALUES (:uid, :role)"),
        {"uid": user_id, "role": role_code},
    )
    db_connection.execute(
        text("INSERT INTO core.user_scope (user_id, scope_type, scope_value) VALUES (:uid, 'LOCATION', :loc)"),
        {"uid": user_id, "loc": location_code},
    )
    token = create_token(user_id, "access", dt.timedelta(minutes=5))
    return {"Authorization": f"Bearer {token}"}


def _seed_receipt(
    db_connection: Connection,
    *,
    location_code: str,
    item_code: str,
    qty: str,
    production_date: dt.date | None = None,
    expiry_date: dt.date | None = None,
) -> None:
    """Direct insert, not through the API, so a test controls the exact
    lot shape it needs — mirrors test_rls_bypass.py's _seed_movement."""
    db_connection.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    db_connection.execute(
        text(
            "INSERT INTO core.stock_movement "
            "(business_date, location_code, item_code, movement_type, qty, uom, "
            " production_date, expiry_date, source_code) "
            "VALUES (:d, :loc, :item, 'RECEIPT', :qty, 'pc', :pd, :ed, 'MANUAL_UPLOAD')"
        ),
        {
            "d": TEST_SENTINEL_DATE,
            "loc": location_code,
            "item": item_code,
            "qty": qty,
            "pd": production_date,
            "ed": expiry_date,
        },
    )


def _balance(db_connection: Connection, location_code: str, item_code: str) -> Decimal:
    db_connection.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    return Decimal(
        db_connection.execute(
            text(
                "SELECT coalesce(sum(qty), 0) FROM core.stock_movement "
                "WHERE location_code = :loc AND item_code = :item AND business_date = :d"
            ),
            {"loc": location_code, "item": item_code, "d": TEST_SENTINEL_DATE},
        ).scalar_one()
    )


def _movements(db_connection: Connection, ref_doc_id: str) -> list:
    db_connection.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    return list(
        db_connection.execute(
            text(
                "SELECT location_code, movement_type, qty, production_date, expiry_date, reason_code "
                "FROM core.stock_movement WHERE ref_doc_type = 'TRANSFER' AND ref_doc_id = :ref "
                "ORDER BY movement_id"
            ),
            {"ref": ref_doc_id},
        ).all()
    )


def _create(client: TestClient, headers: dict[str, str], source: str, dest: str, lines: list[dict]) -> dict:
    response = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"source_location_code": source, "dest_location_code": dest, "lines": lines},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- DB-layer, API bypassed (AC-3/AC-5 style) --------------------------------


def test_in_transit_carve_out_allows_insert_for_a_normally_scoped_user() -> None:
    """The RLS carve-out added by migration 0016: a user scoped to a real
    branch (not unrestricted) must still be able to post a movement at
    the TRANSIT location, or every transfer's in-transit leg would be
    rejected for anyone except a SYS_ADMIN-style unrestricted user."""
    with _app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("SELECT set_config('app.location_scope', :v, true)"), {"v": SOURCE})
            conn.execute(text("SELECT set_config('app.unrestricted', 'off', true)"))
            conn.execute(
                text(
                    "INSERT INTO core.stock_movement "
                    "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
                    "VALUES (:d, 'TRANSIT', :item, 'TRANSFER_IN', 1, 'pc', 'MANUAL_UPLOAD')"
                ),
                {"d": TEST_SENTINEL_DATE, "item": MULTI_DAY_ITEM},
            )  # no exception = pass
        finally:
            tx.rollback()


def test_carve_out_does_not_widen_scope_to_other_real_branches() -> None:
    """The same policy change must not have accidentally loosened the
    general case — a scoped user is still rejected for any branch outside
    their scope, TRANSIT excepted."""
    with _app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("SELECT set_config('app.location_scope', :v, true)"), {"v": SOURCE})
            conn.execute(text("SELECT set_config('app.unrestricted', 'off', true)"))
            with pytest.raises(ProgrammingError, match="row-level security"):
                conn.execute(
                    text(
                        "INSERT INTO core.stock_movement "
                        "(business_date, location_code, item_code, movement_type, qty, uom, source_code) "
                        "VALUES (:d, :loc, :item, 'OPENING', 1, 'pc', 'MANUAL_UPLOAD')"
                    ),
                    {"d": TEST_SENTINEL_DATE, "loc": DEST, "item": MULTI_DAY_ITEM},
                )
        finally:
            tx.rollback()


def test_transfer_table_rls_is_configured() -> None:
    with _app_engine.connect() as conn:
        for table in ("transfer", "transfer_line"):
            row = conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    f"WHERE oid = 'core.{table}'::regclass"
                )
            ).one()
            assert row.relrowsecurity is True
            assert row.relforcerowsecurity is True


# --- Visibility: either side in scope ----------------------------------------


def test_transfer_visible_to_a_user_scoped_only_to_the_destination(
    client: TestClient, db_connection: Connection
) -> None:
    creator = login_as_role(db_connection, "STORE_HEAD")
    transfer = _create(client, creator, SOURCE, DEST, [{"item_code": MULTI_DAY_ITEM, "qty_requested": "1"}])

    dest_only = _login_scoped_to(db_connection, "STORE_HEAD", DEST)
    response = client.get(f"/api/v1/transfers/{transfer['transfer_id']}", headers=dest_only)
    assert response.status_code == 200, response.text


def test_transfer_not_visible_to_a_user_scoped_to_neither_side(
    client: TestClient, db_connection: Connection
) -> None:
    creator = login_as_role(db_connection, "STORE_HEAD")
    transfer = _create(client, creator, SOURCE, DEST, [{"item_code": MULTI_DAY_ITEM, "qty_requested": "1"}])

    stranger = _login_scoped_to(db_connection, "STORE_HEAD", THIRD)
    response = client.get(f"/api/v1/transfers/{transfer['transfer_id']}", headers=stranger)
    assert response.status_code == 404, response.text


# --- ship/receive scope enforcement ------------------------------------------


def test_create_requires_source_scope(client: TestClient, db_connection: Connection) -> None:
    dest_only = _login_scoped_to(db_connection, "STORE_HEAD", DEST)
    response = client.post(
        "/api/v1/transfers",
        headers=dest_only,
        json={
            "source_location_code": SOURCE,
            "dest_location_code": DEST,
            "lines": [{"item_code": MULTI_DAY_ITEM, "qty_requested": "1"}],
        },
    )
    assert response.status_code == 403, response.text


def test_ship_requires_source_scope_not_dest_scope(client: TestClient, db_connection: Connection) -> None:
    creator = login_as_role(db_connection, "STORE_HEAD")
    transfer = _create(client, creator, SOURCE, DEST, [{"item_code": MULTI_DAY_ITEM, "qty_requested": "1"}])

    dest_only = _login_scoped_to(db_connection, "STORE_HEAD", DEST)
    response = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=dest_only,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": MULTI_DAY_ITEM, "qty_shipped": "1"}]},
    )
    assert response.status_code == 403, response.text


def test_receive_requires_dest_scope_not_source_scope(client: TestClient, db_connection: Connection) -> None:
    creator = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="10")
    transfer = _create(client, creator, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "5"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=creator,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "5"}]},
    ).raise_for_status()

    source_only = _login_scoped_to(db_connection, "STORE_HEAD", SOURCE)
    response = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=source_only,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [{"item_code": SAME_DAY_ITEM, "qty_received": "5"}],
        },
    )
    assert response.status_code == 403, response.text


# --- happy path: ship then receive -------------------------------------------


def test_ship_then_receive_equal_quantities_zeroes_in_transit(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")
    source_before = _balance(db_connection, SOURCE, SAME_DAY_ITEM)

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    ship = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    )
    assert ship.status_code == 200, ship.text

    receive = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [{"item_code": SAME_DAY_ITEM, "qty_received": "10"}],
        },
    )
    assert receive.status_code == 200, receive.text
    assert receive.json()["status"] == "RECEIVED"

    source_after = _balance(db_connection, SOURCE, SAME_DAY_ITEM)
    dest_after = _balance(db_connection, DEST, SAME_DAY_ITEM)
    transit_after = _balance(db_connection, "TRANSIT", SAME_DAY_ITEM)

    assert source_after == source_before - 10
    assert dest_after == 10
    assert transit_after == 0

    rows = _movements(db_connection, transfer["transfer_no"])
    assert len(rows) == 4  # ship: source-out + transit-in; receive: transit-out + dest-in
    assert {(r.location_code, r.movement_type) for r in rows} == {
        (SOURCE, "TRANSFER_OUT"),
        ("TRANSIT", "TRANSFER_IN"),
        ("TRANSIT", "TRANSFER_OUT"),
        (DEST, "TRANSFER_IN"),
    }


def test_lot_identity_survives_ship_and_receive_across_two_lots(
    client: TestClient, db_connection: Connection
) -> None:
    """Rule 3: the destination movement copies the SOURCE lot's
    production_date/expiry_date, never today's date, and a line spanning
    two lots posts two movement rows, oldest lot first."""
    headers = login_as_role(db_connection, "STORE_HEAD")
    older_pd = TEST_SENTINEL_DATE
    newer_pd = TEST_SENTINEL_DATE + dt.timedelta(days=1)
    expiry = TEST_SENTINEL_DATE + dt.timedelta(days=3)
    _seed_receipt(
        db_connection, location_code=SOURCE, item_code=MULTI_DAY_ITEM, qty="5",
        production_date=older_pd, expiry_date=expiry,
    )
    _seed_receipt(
        db_connection, location_code=SOURCE, item_code=MULTI_DAY_ITEM, qty="5",
        production_date=newer_pd, expiry_date=expiry + dt.timedelta(days=1),
    )

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": MULTI_DAY_ITEM, "qty_requested": "8"}])
    ship = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [{"item_code": MULTI_DAY_ITEM, "qty_shipped": "8"}],
        },
    )
    assert ship.status_code == 200, ship.text

    ship_out_rows = [r for r in _movements(db_connection, transfer["transfer_no"]) if r.movement_type == "TRANSFER_OUT" and r.location_code == SOURCE]
    assert {(r.production_date, -r.qty) for r in ship_out_rows} == {(older_pd, Decimal("5")), (newer_pd, Decimal("3"))}

    receive = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [{"item_code": MULTI_DAY_ITEM, "qty_received": "8"}],
        },
    )
    assert receive.status_code == 200, receive.text

    dest_in_rows = [r for r in _movements(db_connection, transfer["transfer_no"]) if r.movement_type == "TRANSFER_IN" and r.location_code == DEST]
    assert {(r.production_date, r.qty) for r in dest_in_rows} == {(older_pd, Decimal("5")), (newer_pd, Decimal("3"))}
    # Neither destination row invented today's date — both trace back to a real source lot.
    assert all(r.production_date in (older_pd, newer_pd) for r in dest_in_rows)


def test_short_receipt_variance_posts_adjustment_and_zeroes_in_transit(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    receive = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [
                {"item_code": SAME_DAY_ITEM, "qty_received": "8", "variance_reason_code": "SHORT_RECEIPT"}
            ],
        },
    )
    assert receive.status_code == 200, receive.text

    transit_after = _balance(db_connection, "TRANSIT", SAME_DAY_ITEM)
    dest_after = _balance(db_connection, DEST, SAME_DAY_ITEM)
    assert transit_after == 0
    assert dest_after == 8

    rows = _movements(db_connection, transfer["transfer_no"])
    adjustments = [r for r in rows if r.movement_type == "COUNT_ADJUSTMENT"]
    assert len(adjustments) == 1
    assert adjustments[0].qty == Decimal("-2")
    assert adjustments[0].reason_code == "SHORT_RECEIPT"


def test_receive_requires_variance_reason_when_mismatched(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    receive = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=headers,
        json={
            "business_date": str(TEST_SENTINEL_DATE),
            "lines": [{"item_code": SAME_DAY_ITEM, "qty_received": "8"}],
        },
    )
    assert receive.status_code == 422, receive.text


# --- same-day gate (hard block) ----------------------------------------------


def test_same_day_item_cannot_be_received_on_a_later_business_date(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    next_day = TEST_SENTINEL_DATE + dt.timedelta(days=1)
    receive = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/receive",
        headers=headers,
        json={"business_date": str(next_day), "lines": [{"item_code": SAME_DAY_ITEM, "qty_received": "10"}]},
    )
    assert receive.status_code == 422, receive.text
    assert "same business date" in receive.text


# --- idempotent replay --------------------------------------------------------


def test_ship_replay_with_same_idempotency_key_posts_nothing_extra(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")
    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])

    ship_headers = {**headers, "Idempotency-Key": "test-ship-key-1"}
    body = {"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]}

    first = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/ship", headers=ship_headers, json=body)
    assert first.status_code == 200, first.text
    count_after_first = len(_movements(db_connection, transfer["transfer_no"]))

    second = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/ship", headers=ship_headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(_movements(db_connection, transfer["transfer_no"])) == count_after_first


def test_receive_replay_with_same_idempotency_key_posts_nothing_extra(
    client: TestClient, db_connection: Connection
) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")
    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    receive_headers = {**headers, "Idempotency-Key": "test-receive-key-1"}
    body = {
        "business_date": str(TEST_SENTINEL_DATE),
        "lines": [{"item_code": SAME_DAY_ITEM, "qty_received": "10"}],
    }

    first = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/receive", headers=receive_headers, json=body)
    assert first.status_code == 200, first.text
    count_after_first = len(_movements(db_connection, transfer["transfer_no"]))

    second = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/receive", headers=receive_headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(_movements(db_connection, transfer["transfer_no"])) == count_after_first


# --- state machine ------------------------------------------------------------


def test_cancel_valid_before_ship(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "1"}])
    response = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/cancel", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


def test_cancel_invalid_after_ship(client: TestClient, db_connection: Connection) -> None:
    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")
    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    response = client.post(f"/api/v1/transfers/{transfer['transfer_id']}/cancel", headers=headers)
    assert response.status_code == 409, response.text


# --- gate 1: warn, never block ------------------------------------------------


def test_understocked_source_warns_but_does_not_block(client: TestClient, db_connection: Connection) -> None:
    """Gate 1: the ledger lags reality at branch level — a rider can still
    move real bread even if the recorded balance is short. Create AND ship
    must both succeed, with a warning surfaced, not an error."""
    headers = login_as_role(db_connection, "STORE_HEAD")
    # No receipt seeded at all — recorded balance is 0.
    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": MULTI_DAY_ITEM, "qty_requested": "5"}])
    assert any("only" in w for w in transfer["warnings"])

    ship = client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": MULTI_DAY_ITEM, "qty_shipped": "5"}]},
    )
    assert ship.status_code == 200, ship.text
    # No ledger-backed lot to attribute the shortfall to — posted with no production_date.
    out_row = next(
        r for r in _movements(db_connection, transfer["transfer_no"])
        if r.movement_type == "TRANSFER_OUT" and r.location_code == SOURCE
    )
    assert out_row.production_date is None


# --- transfers excluded from sales/excess metrics ----------------------------


def test_transfer_movements_do_not_affect_excess_or_sales_metrics(
    client: TestClient, db_connection: Connection
) -> None:
    """AC-5: transferred units appear in neither sales_qty nor excess at
    either branch. app.domain.ledger.excess_summary already filters
    strictly to RECEIPT/SALE movement_type (not a blanket sum) — this
    pins that behavior against a real TRANSFER_IN/OUT pair so a future
    change to that filter can't regress it silently."""
    from sqlalchemy.orm import Session as OrmSession

    from app.domain.ledger import excess_summary

    headers = login_as_role(db_connection, "STORE_HEAD")
    _seed_receipt(db_connection, location_code=SOURCE, item_code=SAME_DAY_ITEM, qty="20")

    session = OrmSession(bind=db_connection, join_transaction_mode="create_savepoint")
    session.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    before = excess_summary(session, SOURCE, SAME_DAY_ITEM, TEST_SENTINEL_DATE)

    transfer = _create(client, headers, SOURCE, DEST, [{"item_code": SAME_DAY_ITEM, "qty_requested": "10"}])
    client.post(
        f"/api/v1/transfers/{transfer['transfer_id']}/ship",
        headers=headers,
        json={"business_date": str(TEST_SENTINEL_DATE), "lines": [{"item_code": SAME_DAY_ITEM, "qty_shipped": "10"}]},
    ).raise_for_status()

    session.execute(text("SELECT set_config('app.unrestricted', 'on', true)"))
    after = excess_summary(session, SOURCE, SAME_DAY_ITEM, TEST_SENTINEL_DATE)
    assert after.deliveries_qty == before.deliveries_qty
    assert after.sales_qty == before.sales_qty
    session.close()
