"""Delivery receiving — SPEC §13 GET/POST /api/v1/receiving.

One call covers one delivery (one location, one business_date, one or more
item lines) — a DR (Delivery Receipt, per the domain glossary in SPEC §1)
is naturally multi-item, so this doesn't force one HTTP call per line.

Editing a day's receiving (SPEC: the UI loads what's already on file for a
branch/date and lets the user change it) can never UPDATE/DELETE the
original core.stock_movement rows — the ledger is append-only (CLAUDE.md
DATA). Every POST here is therefore a *diff*: the submitted lines describe
the desired net quantity per item, and this endpoint writes only the
correction needed to get there — a fresh RECEIPT for a genuinely new item,
a COUNT_ADJUSTMENT delta for a changed one (mirroring stock.py's own manual
adjustment, the existing precedent for "correct without rewriting
history"), and a zeroing COUNT_ADJUSTMENT for an item silently dropped from
the resubmission (removed from the table = "this shouldn't have been
received"). GET and POST both return the same net-state shape so the
frontend can just replace its table with whatever comes back.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item, StockMovement

router = APIRouter(prefix="/api/v1/receiving", tags=["receiving"])

# What counts as "today's receiving for this item" when computing the net
# state to diff against — the original entry (RECEIPT/DR) plus any prior
# corrections made through this same endpoint (COUNT_ADJUSTMENT/
# RECEIVING_CORRECTION). A COUNT_ADJUSTMENT from an unrelated physical
# count is a different ref_doc_type and never included here.
_RECEIVING_MOVEMENT_TYPES = ("RECEIPT", "COUNT_ADJUSTMENT")
_RECEIVING_REF_DOC_TYPES = ("DR", "RECEIVING_CORRECTION")


class ReceivingLineIn(BaseModel):
    item_code: str
    qty: Decimal  # the desired *net* quantity for this item today, not a delta
    production_date: dt.date | None = None  # enables FEFO for MULTI_DAY items
    expiry_date: dt.date | None = None  # derived from item.shelf_life_days if omitted
    unit_cost: Decimal | None = None


class ReceivingRequest(BaseModel):
    business_date: dt.date
    location_code: str
    ref_doc_id: str | None = None  # DR number, if the client has one
    confirmed_by_name: str | None = None  # who physically handled the delivery, if not the caller
    lines: list[ReceivingLineIn]


class ReceivingLineOut(BaseModel):
    item_code: str
    qty: Decimal  # net quantity on file for this item today
    uom: str
    production_date: dt.date | None
    unit_cost: Decimal | None
    ref_doc_id: str | None
    confirmed_by_name: str | None
    confirmed_by_user_id: int | None
    confirmed_by_full_name: str | None
    updated_at: dt.datetime | None  # when the line's latest movement/correction was written


def _net_receiving_lines(
    session: Session, location_code: str, business_date: dt.date
) -> list[ReceivingLineOut]:
    """The current net-quantity-per-item state for one branch/date, plus
    each item's most recently touched metadata (production date, who
    confirmed it) — set-based, two queries total regardless of how many
    items are on file, never one query per item.
    """
    sums = session.execute(
        select(StockMovement.item_code, func.sum(StockMovement.qty).label("net_qty"))
        .where(
            StockMovement.location_code == location_code,
            StockMovement.business_date == business_date,
            StockMovement.movement_type.in_(_RECEIVING_MOVEMENT_TYPES),
            StockMovement.ref_doc_type.in_(_RECEIVING_REF_DOC_TYPES),
        )
        .group_by(StockMovement.item_code)
        .having(func.sum(StockMovement.qty) != 0)
    ).all()
    if not sums:
        return []
    net_qty_by_item = {row.item_code: Decimal(row.net_qty) for row in sums}

    # DISTINCT ON (item_code) ordered by created_at desc: the latest row
    # touching each item, which is what "currently on file" should reflect
    # after a correction — same pattern as core.v_effective_price's own
    # DISTINCT ON use (migration 0002).
    latest_rows = session.execute(
        select(StockMovement, AppUser.full_name)
        .distinct(StockMovement.item_code)
        .outerjoin(AppUser, AppUser.user_id == StockMovement.created_by)
        .where(
            StockMovement.location_code == location_code,
            StockMovement.business_date == business_date,
            StockMovement.item_code.in_(net_qty_by_item.keys()),
            StockMovement.movement_type.in_(_RECEIVING_MOVEMENT_TYPES),
            StockMovement.ref_doc_type.in_(_RECEIVING_REF_DOC_TYPES),
        )
        .order_by(StockMovement.item_code, StockMovement.created_at.desc())
    ).all()

    return [
        ReceivingLineOut(
            item_code=movement.item_code,
            qty=net_qty_by_item[movement.item_code],
            uom=movement.uom,
            production_date=movement.production_date,
            unit_cost=movement.unit_cost,
            ref_doc_id=movement.ref_doc_id,
            confirmed_by_name=movement.confirmed_by_name,
            confirmed_by_user_id=movement.created_by,
            confirmed_by_full_name=full_name,
            updated_at=movement.created_at,
        )
        for movement, full_name in latest_rows
    ]


@router.get("", response_model=list[ReceivingLineOut])
def get_receiving(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("receiving.confirm"))],
    location_code: str = Query(...),
    business_date: dt.date = Query(...),
) -> list[ReceivingLineOut]:
    """What's currently on file for one branch/date — powers the Receiving
    screen's edit view. Empty list means nothing has been received there
    yet today, not an error.
    """
    return _net_receiving_lines(session, location_code, business_date)


@router.post("", response_model=list[ReceivingLineOut], status_code=201)
def confirm_receiving(
    body: ReceivingRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("receiving.confirm"))],
) -> list[ReceivingLineOut]:
    existing = {line.item_code: line.qty for line in _net_receiving_lines(session, body.location_code, body.business_date)}

    if not body.lines and not existing:
        raise HTTPException(status_code=422, detail="At least one line is required")

    submitted_items = {line.item_code for line in body.lines}

    for line in body.lines:
        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")

        current_qty = existing.get(line.item_code, Decimal(0))
        delta = line.qty - current_qty
        if delta == 0:
            continue  # nothing actually changed for this item

        expiry_date = line.expiry_date
        if expiry_date is None and line.production_date is not None and item.shelf_life_days > 0:
            expiry_date = line.production_date + dt.timedelta(days=item.shelf_life_days)

        is_new_line = current_qty == 0
        try:
            write_movement(
                session,
                business_date=body.business_date,
                location_code=body.location_code,
                item_code=line.item_code,
                movement_type="RECEIPT" if is_new_line else "COUNT_ADJUSTMENT",
                qty=delta,
                uom=item.base_uom,
                production_date=line.production_date,
                expiry_date=expiry_date,
                unit_cost=line.unit_cost,
                ref_doc_type="DR" if is_new_line else "RECEIVING_CORRECTION",
                ref_doc_id=body.ref_doc_id,
                confirmed_by_name=body.confirmed_by_name,
                created_by=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{line.item_code}: {exc}") from exc

    # Anything on file that the resubmission silently dropped is being
    # zeroed out, not just forgotten — removing a row from the table means
    # "this shouldn't have been received."
    for item_code, current_qty in existing.items():
        if item_code in submitted_items or current_qty == 0:
            continue
        item = session.get(Item, item_code)
        if item is None:
            continue
        write_movement(
            session,
            business_date=body.business_date,
            location_code=body.location_code,
            item_code=item_code,
            movement_type="COUNT_ADJUSTMENT",
            qty=-current_qty,
            uom=item.base_uom,
            ref_doc_type="RECEIVING_CORRECTION",
            ref_doc_id=body.ref_doc_id,
            confirmed_by_name=body.confirmed_by_name,
            created_by=user.user_id,
        )

    return _net_receiving_lines(session, body.location_code, body.business_date)
