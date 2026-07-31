"""The stock ledger's read/write core. Implements SPEC §4.4.

write_movement is the only path application code should use to create a
core.stock_movement row — never construct and add() one directly from a
router, so the sign-convention and idempotency rules below live in one
place, not copy-pasted across receiving/waste/transfers/adjustments.

FEFO note: the ledger records production_date on a movement but has no
explicit link from an outgoing movement to the specific inbound batch it
depleted (no batch_id). fefo_ageing therefore nets SUM(qty) per
production_date directly — correct only if callers that consume a specific
batch (waste, a transfer, a future POS sale) stamp the outgoing movement
with that batch's production_date. This phase's waste/transfer endpoints
accept an explicit production_date for exactly that reason; see app/api/v1.
"""
import datetime as dt
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StockMovement

# SPEC §4.4: "qty signed: +in, -out". COUNT_ADJUSTMENT is deliberately
# excluded from both sets — a cycle count can correct a balance in either
# direction, so its sign is legitimately data-dependent rather than fixed
# by movement_type.
_POSITIVE_MOVEMENT_TYPES = frozenset({"RECEIPT", "PRODUCTION", "RETURN", "TRANSFER_IN", "OPENING"})
_NEGATIVE_MOVEMENT_TYPES = frozenset({"SALE", "WASTE", "TRANSFER_OUT", "CONSUMPTION"})


class FefoBucket(NamedTuple):
    production_date: dt.date
    expiry_date: dt.date | None
    remaining_qty: Decimal
    days_remaining: int | None  # None if expiry_date was never stamped on any movement in the batch


def balance_as_of(
    session: Session, location_code: str, item_code: str, as_of_date: dt.date
) -> Decimal:
    """Signed sum of every movement up to and including as_of_date — the
    ledger balance is always well-defined (SPEC §4.4: balances are derived,
    never stored), so an empty result is a genuine zero, not a "not
    counted" absence. That distinction (CLAUDE.md DATA) applies to raw
    input facts like a count or a sales figure, not to this aggregate.

    This is what populates count_line.expected_qty — see app.api.v1.counts.
    """
    total = session.execute(
        select(func.coalesce(func.sum(StockMovement.qty), 0)).where(
            StockMovement.location_code == location_code,
            StockMovement.item_code == item_code,
            StockMovement.business_date <= as_of_date,
        )
    ).scalar_one()
    return Decimal(total)


def fefo_ageing(
    session: Session, location_code: str, item_code: str, as_of_date: dt.date
) -> list[FefoBucket]:
    """Remaining quantity per production batch, oldest first (First-Expired-
    First-Out order) — for MULTI_DAY items only; a same-day item's movements
    carry no production_date and this simply returns nothing for one.

    Grouped by production_date ALONE, not (production_date, expiry_date): a
    consuming movement (waste, a transfer out) may stamp only production_date
    to identify which batch it drew from, without repeating that batch's
    expiry_date. Grouping on the pair would silently split such a row into
    its own bucket instead of netting it against the batch it actually
    depleted — max(expiry_date) recovers the date from whichever row in the
    batch did record it (normally the RECEIPT) while still netting every
    row sharing that production_date together.
    """
    rows = session.execute(
        select(
            StockMovement.production_date,
            func.max(StockMovement.expiry_date).label("expiry_date"),
            func.sum(StockMovement.qty).label("remaining_qty"),
        )
        .where(
            StockMovement.location_code == location_code,
            StockMovement.item_code == item_code,
            StockMovement.production_date.is_not(None),
            StockMovement.business_date <= as_of_date,
        )
        .group_by(StockMovement.production_date)
        .having(func.sum(StockMovement.qty) > 0)
        .order_by(StockMovement.production_date.asc())
    ).all()

    return [
        FefoBucket(
            production_date=row.production_date,
            expiry_date=row.expiry_date,
            remaining_qty=Decimal(row.remaining_qty),
            days_remaining=(row.expiry_date - as_of_date).days if row.expiry_date else None,
        )
        for row in rows
    ]


def write_movement(
    session: Session,
    *,
    business_date: dt.date,
    location_code: str,
    item_code: str,
    movement_type: str,
    qty: Decimal,
    uom: str,
    created_by: int,
    production_date: dt.date | None = None,
    expiry_date: dt.date | None = None,
    unit_cost: Decimal | None = None,
    reason_code: str | None = None,
    ref_doc_type: str | None = None,
    ref_doc_id: str | None = None,
    counterparty_location: str | None = None,
    source_code: str | None = None,
    idempotency_key: str | None = None,
) -> StockMovement:
    """Inserts one core.stock_movement row. The only place application code
    should do this — receiving/waste/transfers/adjustments all call this
    rather than constructing StockMovement themselves.

    Raises ValueError if qty's sign contradicts movement_type's documented
    direction (SPEC §4.4). Never silently flips the sign: a caller passing
    the wrong sign has a bug worth surfacing, not one worth papering over.

    Idempotency: if idempotency_key is given and a movement already exists
    for (business_date, idempotency_key), returns that existing row instead
    of inserting a duplicate (uq_movement_idem). Check-first, not
    ON CONFLICT — acceptable here because these are interactive, human-typed
    submissions (the realistic duplicate is a double-submitted form, not
    concurrent automated replay); the staging/ingest pipeline that handles
    genuine concurrent replay is out of scope for this phase.
    """
    if movement_type in _POSITIVE_MOVEMENT_TYPES and qty <= 0:
        raise ValueError(f"{movement_type} requires a positive qty, got {qty}")
    if movement_type in _NEGATIVE_MOVEMENT_TYPES and qty >= 0:
        raise ValueError(f"{movement_type} requires a negative qty, got {qty}")

    if idempotency_key is not None:
        existing = session.execute(
            select(StockMovement).where(
                StockMovement.business_date == business_date,
                StockMovement.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    movement = StockMovement(
        business_date=business_date,
        location_code=location_code,
        item_code=item_code,
        movement_type=movement_type,
        qty=qty,
        uom=uom,
        production_date=production_date,
        expiry_date=expiry_date,
        unit_cost=unit_cost,
        reason_code=reason_code,
        ref_doc_type=ref_doc_type,
        ref_doc_id=ref_doc_id,
        counterparty_location=counterparty_location,
        source_code=source_code,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
    session.add(movement)
    session.flush()  # populate movement_id/occurred_at/created_at for the caller
    return movement
