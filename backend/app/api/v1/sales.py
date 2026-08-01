"""Sales (offtake) recording — SPEC §1's "Sold"/"Offtake" glossary term.

One call covers one branch/day, one or more item lines — mirrors
app.api.v1.receiving's shape (GET loads what's on file, POST is a diff
against it, never a raw insert), for the same reason: core.stock_movement
is append-only, so "editing" a day's sales can never UPDATE/DELETE the
original SALE rows. A changed quantity writes a COUNT_ADJUSTMENT delta
(mirroring receiving.py and stock.py's own manual-adjustment precedent); an
item silently dropped from the resubmission is zeroed out via the same
mechanism, not forgotten.

qty in each line is the positive amount sold; write_movement requires SALE
rows to carry a negative qty (SPEC §4.4's signed convention) — negated at
the point of writing, same as app.api.v1.waste negates waste qty.

A line's sold_out flag writes/clears a core.sold_out_event row (migration
0010) — the signal Stock Explorer's Run Outs indicator reads (see
app.domain.ledger.excess_summary). It is not itself a movement: running out
is a fact about the day, separate from how many units were sold before it
happened. Unlike stock_movement, sold_out_event is a same-day flag, not a
ledger entry — clearing it on edit is a real delete, not an
append-only-rule violation, since there's no "offsetting" way to un-flag a
boolean.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item, SoldOutEvent, StockMovement

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

# Mirrors receiving.py's _RECEIVING_MOVEMENT_TYPES/_REF_DOC_TYPES pair —
# what counts as "today's sales for this item" when computing net state:
# the original entry (SALE) plus any prior corrections made through this
# endpoint (COUNT_ADJUSTMENT/SALES_CORRECTION). A COUNT_ADJUSTMENT from an
# unrelated physical count is a different ref_doc_type and never included.
_SALES_MOVEMENT_TYPES = ("SALE", "COUNT_ADJUSTMENT")
_SALES_REF_DOC_TYPES = ("SALE", "SALES_CORRECTION")


class SalesLineIn(BaseModel):
    item_code: str
    qty: Decimal  # the desired *net* quantity sold today, not a delta
    sold_out: bool = False  # ran out at some point on this business_date


class SalesRequest(BaseModel):
    business_date: dt.date
    location_code: str
    confirmed_by_name: str | None = None  # cashier / who recorded, if not the caller
    lines: list[SalesLineIn]


class SalesLineOut(BaseModel):
    item_code: str
    qty: Decimal  # net quantity sold today, positive
    uom: str
    sold_out: bool
    unit_price: Decimal | None  # core.v_effective_price for this item/branch; None if unpriced
    total_price: Decimal | None  # qty * unit_price; None when unit_price is None
    confirmed_by_name: str | None
    confirmed_by_user_id: int | None
    confirmed_by_full_name: str | None
    updated_at: dt.datetime | None  # when the line's latest movement/correction was written


def _effective_prices(session: Session, location_code: str, item_codes: list[str]) -> dict[str, Decimal]:
    """core.v_effective_price already resolves branch-override-over-network
    (migration 0002) — read it directly rather than re-deriving that
    fallback here. No ORM model exists for this view (it's read-only,
    computed), so this is a plain text() query, expanding-bound like any
    other IN-list against a caller-supplied set of codes.
    """
    if not item_codes:
        return {}
    stmt = text(
        "SELECT item_code, srp FROM core.v_effective_price "
        "WHERE location_code = :loc AND item_code IN :items AND srp IS NOT NULL"
    ).bindparams(bindparam("items", expanding=True))
    rows = session.execute(stmt, {"loc": location_code, "items": item_codes}).all()
    return {row.item_code: row.srp for row in rows}


def _net_sales_lines(session: Session, location_code: str, business_date: dt.date) -> list[SalesLineOut]:
    """The current net-quantity-sold-per-item state for one branch/date,
    plus each item's price and most recently touched metadata — set-based,
    a handful of queries regardless of how many items are on file, never
    one query per item."""
    sums = session.execute(
        select(StockMovement.item_code, func.sum(StockMovement.qty).label("net_qty"))
        .where(
            StockMovement.location_code == location_code,
            StockMovement.business_date == business_date,
            StockMovement.movement_type.in_(_SALES_MOVEMENT_TYPES),
            StockMovement.ref_doc_type.in_(_SALES_REF_DOC_TYPES),
        )
        .group_by(StockMovement.item_code)
        .having(func.sum(StockMovement.qty) != 0)
    ).all()
    if not sums:
        return []
    # SALE is stored negative (SPEC §4.4); the net *sold* quantity a clerk
    # thinks in terms of is the positive magnitude.
    net_qty_by_item = {row.item_code: -Decimal(row.net_qty) for row in sums}

    latest_rows = session.execute(
        select(StockMovement, AppUser.full_name)
        .distinct(StockMovement.item_code)
        .outerjoin(AppUser, AppUser.user_id == StockMovement.created_by)
        .where(
            StockMovement.location_code == location_code,
            StockMovement.business_date == business_date,
            StockMovement.item_code.in_(net_qty_by_item.keys()),
            StockMovement.movement_type.in_(_SALES_MOVEMENT_TYPES),
            StockMovement.ref_doc_type.in_(_SALES_REF_DOC_TYPES),
        )
        .order_by(StockMovement.item_code, StockMovement.created_at.desc())
    ).all()

    sold_out_items = set(
        session.execute(
            select(SoldOutEvent.item_code).where(
                SoldOutEvent.business_date == business_date,
                SoldOutEvent.location_code == location_code,
                SoldOutEvent.item_code.in_(net_qty_by_item.keys()),
            )
        )
        .scalars()
        .all()
    )

    prices = _effective_prices(session, location_code, list(net_qty_by_item.keys()))

    lines = []
    for movement, full_name in latest_rows:
        qty = net_qty_by_item[movement.item_code]
        unit_price = prices.get(movement.item_code)
        lines.append(
            SalesLineOut(
                item_code=movement.item_code,
                qty=qty,
                uom=movement.uom,
                sold_out=movement.item_code in sold_out_items,
                unit_price=unit_price,
                total_price=(qty * unit_price) if unit_price is not None else None,
                confirmed_by_name=movement.confirmed_by_name,
                confirmed_by_user_id=movement.created_by,
                confirmed_by_full_name=full_name,
                updated_at=movement.created_at,
            )
        )
    return lines


def _set_sold_out(
    session: Session, *, business_date: dt.date, location_code: str, item_code: str, wants_flag: bool, created_by: int
) -> None:
    existing = session.execute(
        select(SoldOutEvent).where(
            SoldOutEvent.business_date == business_date,
            SoldOutEvent.location_code == location_code,
            SoldOutEvent.item_code == item_code,
        )
    ).scalar_one_or_none()
    if wants_flag and existing is None:
        session.add(
            SoldOutEvent(
                business_date=business_date, location_code=location_code, item_code=item_code, created_by=created_by
            )
        )
    elif not wants_flag and existing is not None:
        session.delete(existing)


@router.get("", response_model=list[SalesLineOut])
def get_sales(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("sales.record"))],
    location_code: str = Query(...),
    business_date: dt.date = Query(...),
) -> list[SalesLineOut]:
    """What's currently on file for one branch/date — powers the Sales
    screen's edit view. Empty list means nothing has been recorded there
    yet today, not an error."""
    return _net_sales_lines(session, location_code, business_date)


@router.post("", response_model=list[SalesLineOut], status_code=201)
def record_sales(
    body: SalesRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("sales.record"))],
) -> list[SalesLineOut]:
    existing = {line.item_code: line for line in _net_sales_lines(session, body.location_code, body.business_date)}

    if not body.lines and not existing:
        raise HTTPException(status_code=422, detail="At least one line is required")

    submitted_items = {line.item_code for line in body.lines}

    for line in body.lines:
        if line.qty < 0:
            raise HTTPException(status_code=422, detail=f"{line.item_code}: qty cannot be negative")

        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")

        current = existing.get(line.item_code)
        current_qty = current.qty if current else Decimal(0)
        delta = line.qty - current_qty
        is_new_line = current_qty == 0

        if delta != 0:
            try:
                write_movement(
                    session,
                    business_date=body.business_date,
                    location_code=body.location_code,
                    item_code=line.item_code,
                    movement_type="SALE" if is_new_line else "COUNT_ADJUSTMENT",
                    # SALE stores negative; a +delta in "amount sold" is
                    # -delta more leaving stock, and a -delta (an
                    # over-reported sale being walked back) adds +|delta|
                    # back — -delta expresses both directions correctly.
                    qty=-delta,
                    uom=item.base_uom,
                    ref_doc_type="SALE" if is_new_line else "SALES_CORRECTION",
                    confirmed_by_name=body.confirmed_by_name,
                    created_by=user.user_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"{line.item_code}: {exc}") from exc

        _set_sold_out(
            session,
            business_date=body.business_date,
            location_code=body.location_code,
            item_code=line.item_code,
            wants_flag=line.sold_out,
            created_by=user.user_id,
        )

    # Anything on file that the resubmission silently dropped is being
    # zeroed out, not just forgotten — same reasoning as receiving.py.
    for item_code, current in existing.items():
        if item_code in submitted_items or current.qty == 0:
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
            qty=current.qty,  # reverses the previously-recorded sale
            uom=item.base_uom,
            ref_doc_type="SALES_CORRECTION",
            confirmed_by_name=body.confirmed_by_name,
            created_by=user.user_id,
        )
        _set_sold_out(
            session,
            business_date=body.business_date,
            location_code=body.location_code,
            item_code=item_code,
            wants_flag=False,
            created_by=user.user_id,
        )

    return _net_sales_lines(session, body.location_code, body.business_date)
