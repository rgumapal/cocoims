"""Branch-to-branch transfers — docs/features/TRANSFERS_V1.md.

State machine, the three validation gates, FEFO allocation and ledger
posting for transfers. Callers (app/api/v1/transfers.py) own permission
checks (require_permission) and DB-layer scope (Depends(get_db)); this
module owns the business rules that don't belong at either of those
layers — see counts.py's separate-of-duties check for the precedent this
follows (nuanced rules live in the service layer, not routers or RLS).

Everything here posts through app.domain.ledger.write_movement, never a
raw StockMovement insert — see that module's own docstring for why.
"""
import datetime as dt
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.ledger import FefoBucket, balance_as_of, fefo_ageing, write_movement
from app.models import Item, ItemLocationParam, StockMovement, Transfer, TransferLine

IN_TRANSIT_LOCATION_CODE = "TRANSIT"

# DRAFT -> IN_TRANSIT (ship) or CANCELLED. IN_TRANSIT -> RECEIVED (receive).
# RECEIVED and CANCELLED are terminal. No `if status ==` chains in routers —
# every transition check goes through validate_transition below.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"IN_TRANSIT", "CANCELLED"}),
    "IN_TRANSIT": frozenset({"RECEIVED"}),
    "RECEIVED": frozenset(),
    "CANCELLED": frozenset(),
}


def validate_transition(current_status: str, target_status: str) -> None:
    """Raises ValueError if `current_status -> target_status` isn't a legal
    move. The one place transfer.py's state machine is spelled out."""
    if target_status not in _ALLOWED_TRANSITIONS.get(current_status, frozenset()):
        raise ValueError(f"Cannot move a transfer from {current_status} to {target_status}")


class FefoAllocation(NamedTuple):
    """One lot's contribution to a ship or receive posting."""

    production_date: dt.date | None
    expiry_date: dt.date | None
    qty: Decimal


def check_source_stock(
    session: Session, *, location_code: str, item_code: str, business_date: dt.date, qty: Decimal
) -> str | None:
    """Gate 1: does the source have enough recorded stock? Under-stock is a
    warning, never a hard block — the ledger lags physical reality at
    branch level (a count hasn't caught up yet), and the rider is moving
    real bread regardless of what the ledger says. Returns a warning
    string, or None if the recorded balance covers the request."""
    available = balance_as_of(session, location_code, item_code, business_date)
    if available < qty:
        return (
            f"{item_code}: requesting {qty} but only {available} is recorded on hand "
            f"at {location_code} as of {business_date}. Allowed with a reason."
        )
    return None


def check_destination_stocked(session: Session, *, location_code: str, item_code: str) -> str | None:
    """Gate 2: does the destination stock this item? A MISSING
    item_location_param row means "no assortment data recorded", not "not
    stocked" — the onboarding wizard and assortment templates that would
    populate this table aren't built yet (see ItemLocationParam's
    docstring), so treating absence as a block would fail every transfer
    on this prototype's current data. Only an explicit is_stocked=false
    row is a warning."""
    param = session.get(ItemLocationParam, (item_code, location_code))
    if param is not None and not param.is_stocked:
        return f"{item_code}: {location_code} has this item explicitly marked not stocked. Allowed with a reason."
    return None


def check_same_day_only_same_date(
    session: Session, *, transfer_no: str, item: Item, receive_business_date: dt.date
) -> None:
    """Gate 3, hard block: a shelf_life_days=0 item may only be received on
    the same business_date it shipped on. Past that it cannot legally be
    sold on arrival — receiving it later would be relabelling waste as
    inventory, exactly what CLAUDE.md's NULL-is-not-zero DQ discipline
    exists to prevent from happening silently.

    Reads the ship business_date back from the ledger itself (the
    TRANSFER_OUT rows this transfer already posted at ship time) rather
    than storing a redundant column on core.transfer — "the ledger is the
    lot record" applies here too.
    """
    if item.shelf_life_days > 0:
        return
    ship_dates = session.execute(
        select(StockMovement.business_date)
        .where(
            StockMovement.ref_doc_type == "TRANSFER",
            StockMovement.ref_doc_id == transfer_no,
            StockMovement.item_code == item.item_code,
            StockMovement.movement_type == "TRANSFER_OUT",
        )
        .distinct()
    ).scalars().all()
    if any(d != receive_business_date for d in ship_dates):
        raise ValueError(
            f"{item.item_code} has shelf_life_days=0 and shipped on {ship_dates[0]}. "
            f"It cannot be received on {receive_business_date} — same-day items only "
            f"transfer within the same business date."
        )


def _consume_fefo_oldest_first(
    buckets: list, qty_needed: Decimal
) -> tuple[list[FefoAllocation], Decimal]:
    """Consumes `buckets` (already oldest-first, ledger.FefoBucket shape)
    up to qty_needed. Returns (allocations, unfilled_qty) — unfilled_qty
    > 0 means the recorded ledger balance couldn't cover the request
    (gate 1 already warned about this; the caller posts the shortfall with
    no production_date, since there is no ledger-backed lot to attribute
    it to — never fabricate today's date, rule 3)."""
    allocations: list[FefoAllocation] = []
    remaining = qty_needed
    for bucket in buckets:
        if remaining <= 0:
            break
        take = min(bucket.remaining_qty, remaining)
        if take > 0:
            allocations.append(FefoAllocation(bucket.production_date, bucket.expiry_date, take))
            remaining -= take
    return allocations, remaining


def allocate_source_fefo(
    session: Session, *, location_code: str, item_code: str, business_date: dt.date, qty: Decimal
) -> list[FefoAllocation]:
    """FEFO allocation for the ship leg — oldest lot at the source first.
    Reuses ledger.fefo_ageing's bucket query rather than re-deriving it;
    only the consumption walk is new (fefo_ageing reports ageing, it
    doesn't consume)."""
    buckets = fefo_ageing(session, location_code, item_code, business_date)
    allocations, unfilled = _consume_fefo_oldest_first(buckets, qty)
    if unfilled > 0:
        allocations.append(FefoAllocation(None, None, unfilled))
    return allocations


def allocate_in_transit_fefo(
    session: Session, *, item_code: str, transfer_no: str, business_date: dt.date, qty: Decimal
) -> list[FefoAllocation]:
    """FEFO allocation for the receive leg — oldest lot *this transfer
    itself shipped* first. Deliberately scoped to transfer_no rather than
    every lot currently sitting in the shared in-transit bucket: v1 treats
    "receive transfer X" as receiving exactly what X shipped, not as
    drawing from a network-wide in-transit pool that might include other
    transfers' lots. Composed directly rather than through
    ledger.fefo_ageing, which has no ref_doc_id filter — adding one there
    for this single caller would widen a function this codebase already
    tests and relies on elsewhere."""
    rows = session.execute(
        select(
            StockMovement.production_date,
            func.max(StockMovement.expiry_date).label("expiry_date"),
            func.sum(StockMovement.qty).label("remaining_qty"),
        )
        .where(
            StockMovement.location_code == IN_TRANSIT_LOCATION_CODE,
            StockMovement.item_code == item_code,
            StockMovement.ref_doc_type == "TRANSFER",
            StockMovement.ref_doc_id == transfer_no,
            StockMovement.business_date <= business_date,
        )
        .group_by(StockMovement.production_date)
        .having(func.sum(StockMovement.qty) > 0)
        .order_by(StockMovement.production_date.asc().nulls_first())
    ).all()
    buckets = [
        FefoBucket(
            production_date=row.production_date,
            expiry_date=row.expiry_date,
            remaining_qty=Decimal(row.remaining_qty),
            days_remaining=None,
        )
        for row in rows
    ]
    allocations, unfilled = _consume_fefo_oldest_first(buckets, qty)
    if unfilled > 0:
        allocations.append(FefoAllocation(None, None, unfilled))
    return allocations


def post_ship(
    session: Session,
    *,
    transfer: Transfer,
    lines: dict[str, Decimal],
    business_date: dt.date,
    created_by: int,
) -> None:
    """Posts the source -> in-transit leg for every line in `lines`
    (item_code -> qty_shipped). One TRANSFER_OUT/TRANSFER_IN pair per lot
    consumed (rule 3: a line spanning two lots posts two movement rows).
    Same-day items (shelf_life_days=0) skip FEFO — those movements never
    carry a production_date (ledger.fefo_ageing's own convention).

    Caller is responsible for the idempotency check (has this
    ship_idempotency_key already been processed?) *before* calling this —
    it always posts, it never checks for a prior call itself.
    """
    for item_code, qty_shipped in lines.items():
        if qty_shipped <= 0:
            raise ValueError(f"{item_code}: qty_shipped must be positive, got {qty_shipped}")
        item = session.get(Item, item_code)
        if item is None:
            raise ValueError(f"Item {item_code} not found")

        if item.shelf_life_days > 0:
            allocations = allocate_source_fefo(
                session,
                location_code=transfer.source_location_code,
                item_code=item_code,
                business_date=business_date,
                qty=qty_shipped,
            )
        else:
            allocations = [FefoAllocation(None, None, qty_shipped)]

        for alloc in allocations:
            write_movement(
                session,
                business_date=business_date,
                location_code=transfer.source_location_code,
                item_code=item_code,
                movement_type="TRANSFER_OUT",
                qty=-alloc.qty,
                uom=item.base_uom,
                production_date=alloc.production_date,
                expiry_date=alloc.expiry_date,
                ref_doc_type="TRANSFER",
                ref_doc_id=transfer.transfer_no,
                counterparty_location=transfer.dest_location_code,
                created_by=created_by,
            )
            write_movement(
                session,
                business_date=business_date,
                location_code=IN_TRANSIT_LOCATION_CODE,
                item_code=item_code,
                movement_type="TRANSFER_IN",
                qty=alloc.qty,
                uom=item.base_uom,
                production_date=alloc.production_date,
                expiry_date=alloc.expiry_date,
                ref_doc_type="TRANSFER",
                ref_doc_id=transfer.transfer_no,
                counterparty_location=transfer.source_location_code,
                created_by=created_by,
            )

        line = session.get(TransferLine, (transfer.transfer_id, item_code))
        if line is not None:
            line.qty_shipped = qty_shipped
            session.flush()
            session.refresh(line)  # picks up the DB's own NUMERIC(12,3) scale


def post_receive(
    session: Session,
    *,
    transfer: Transfer,
    lines: dict[str, tuple[Decimal, str | None]],
    business_date: dt.date,
    created_by: int,
) -> None:
    """Posts the in-transit -> destination leg. `lines` maps item_code to
    (qty_received, variance_reason_code). Always removes exactly
    qty_shipped from in-transit (what physically left the source), and
    posts qty_received to the destination (what physically arrived) — the
    difference, if any, is posted as its own COUNT_ADJUSTMENT against
    in-transit so that bucket always nets to zero once every line on a
    transfer is received, per rule "the service posts the difference
    against in-transit as an adjustment" (docs/features/TRANSFERS_V1.md).

    Caller is responsible for: the idempotency check, gate 3 (same-day
    same-date), and requiring variance_reason_code when shipped != received
    — this function trusts its inputs and just posts them.
    """
    for item_code, (qty_received, variance_reason_code) in lines.items():
        if qty_received < 0:
            raise ValueError(f"{item_code}: qty_received cannot be negative, got {qty_received}")
        item = session.get(Item, item_code)
        line = session.get(TransferLine, (transfer.transfer_id, item_code))
        if item is None or line is None or line.qty_shipped is None:
            raise ValueError(f"{item_code} was never shipped on this transfer")
        qty_shipped = line.qty_shipped

        if item.shelf_life_days > 0:
            allocations = allocate_in_transit_fefo(
                session,
                item_code=item_code,
                transfer_no=transfer.transfer_no or str(transfer.transfer_id),
                business_date=business_date,
                qty=qty_received,
            )
        else:
            allocations = [FefoAllocation(None, None, qty_received)] if qty_received > 0 else []

        for alloc in allocations:
            write_movement(
                session,
                business_date=business_date,
                location_code=IN_TRANSIT_LOCATION_CODE,
                item_code=item_code,
                movement_type="TRANSFER_OUT",
                qty=-alloc.qty,
                uom=item.base_uom,
                production_date=alloc.production_date,
                expiry_date=alloc.expiry_date,
                ref_doc_type="TRANSFER",
                ref_doc_id=transfer.transfer_no,
                counterparty_location=transfer.dest_location_code,
                created_by=created_by,
            )
            write_movement(
                session,
                business_date=business_date,
                location_code=transfer.dest_location_code,
                item_code=item_code,
                movement_type="TRANSFER_IN",
                qty=alloc.qty,
                uom=item.base_uom,
                production_date=alloc.production_date,
                expiry_date=alloc.expiry_date,
                ref_doc_type="TRANSFER",
                ref_doc_id=transfer.transfer_no,
                counterparty_location=transfer.source_location_code,
                created_by=created_by,
            )

        variance = qty_received - qty_shipped
        if variance != 0:
            write_movement(
                session,
                business_date=business_date,
                location_code=IN_TRANSIT_LOCATION_CODE,
                item_code=item_code,
                movement_type="COUNT_ADJUSTMENT",
                qty=variance,
                uom=item.base_uom,
                reason_code=variance_reason_code,
                ref_doc_type="TRANSFER",
                ref_doc_id=transfer.transfer_no,
                created_by=created_by,
            )

        line.qty_received = qty_received
        line.variance_reason_code = variance_reason_code
        session.flush()
        session.refresh(line)  # variance_qty is DB-generated — see post_ship's own refresh for why
