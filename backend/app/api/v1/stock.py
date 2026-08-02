"""Stock visibility and manual ledger adjustments — SPEC §13.

Every write here goes through app.domain.ledger.write_movement, never a
direct StockMovement(...) construction, so the sign-convention and
idempotency rules stay in one place (see that module's docstring).
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.pagination import Page
from app.auth.deps import get_db, require_permission
from app.domain.ledger import (
    balance_as_of,
    excess_summary,
    fefo_ageing,
    location_stock_summary,
    write_movement,
)
from app.models import AppUser, StockMovement

router = APIRouter(prefix="/api/v1/stock", tags=["stock"])


class FefoBucketOut(BaseModel):
    production_date: dt.date
    expiry_date: dt.date | None
    remaining_qty: Decimal
    days_remaining: int | None


class StockBalanceOut(BaseModel):
    location_code: str
    item_code: str
    as_of_date: dt.date
    balance_qty: Decimal
    fefo_buckets: list[FefoBucketOut]
    # Excess/Run Outs (SPEC §1 glossary), computed live from stock_movement
    # — see app.domain.ledger.excess_summary's docstring for why this is
    # all-time-to-date rather than a rolling window, and why excess_qty is
    # not floored at zero.
    deliveries_qty: Decimal
    sales_qty: Decimal
    excess_qty: Decimal
    excess_pct: Decimal | None
    sold_out_dates: list[dt.date]


class LocationItemStockOut(BaseModel):
    item_code: str
    display_name: str
    received_qty: Decimal
    deducted_qty: Decimal
    balance_qty: Decimal
    excess_pct: Decimal | None
    run_outs: int


class StockMovementOut(BaseModel):
    business_date: dt.date
    movement_id: int
    occurred_at: dt.datetime | None
    location_code: str
    item_code: str
    movement_type: str
    qty: Decimal
    uom: str
    production_date: dt.date | None
    expiry_date: dt.date | None
    unit_cost: Decimal | None
    reason_code: str | None
    ref_doc_type: str | None
    ref_doc_id: str | None
    counterparty_location: str | None
    source_code: str | None

    model_config = {"from_attributes": True}


class ManualAdjustmentRequest(BaseModel):
    business_date: dt.date
    location_code: str
    item_code: str
    qty: Decimal  # signed — see app.domain.ledger's sign convention
    uom: str
    reason_code: str  # required for a manual adjustment (SPEC §7.4: no override without a reason)
    # No free-text note: core.stock_movement has no note column to store one
    # in, and accepting a field that's silently discarded would be worse
    # than not accepting it — reason_code is the structured field this row
    # actually persists.


@router.get("/by-location", response_model=list[LocationItemStockOut])
def list_stock_by_location(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("order.read"))],
    location: str = Query(...),
    as_of: dt.date | None = Query(default=None, description="Defaults to today"),
) -> list[LocationItemStockOut]:
    """Every item with ledger history at one branch, as of one date —
    what Stock Explorer shows immediately after picking a branch, before
    any single item is selected. Each row's balance is broken into
    received vs. deducted so it's never just a bare number (SPEC's Ladder
    Trace principle: any quantity should show its derivation). RLS scopes
    `location` automatically, same as GET /stock.
    """
    as_of_date = as_of or dt.date.today()
    rows = location_stock_summary(session, location, as_of_date)
    return [LocationItemStockOut(**row._asdict()) for row in rows]


@router.get("", response_model=StockBalanceOut)
def get_stock_balance(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("order.read"))],
    location: str = Query(...),
    item: str = Query(...),
    as_of: dt.date | None = Query(default=None, description="Defaults to today"),
) -> StockBalanceOut:
    """Current ledger balance plus FEFO ageing buckets for one item at one
    branch. RLS scopes `location` automatically — an out-of-scope location
    simply returns a zero balance and no buckets, the same way any other
    scoped SELECT does (SPEC §7.4: absent scope returns an empty result,
    never another branch's data).
    """
    as_of_date = as_of or dt.date.today()
    balance = balance_as_of(session, location, item, as_of_date)
    buckets = fefo_ageing(session, location, item, as_of_date)
    excess = excess_summary(session, location, item, as_of_date)
    return StockBalanceOut(
        location_code=location,
        item_code=item,
        as_of_date=as_of_date,
        balance_qty=balance,
        fefo_buckets=[FefoBucketOut(**b._asdict()) for b in buckets],
        deliveries_qty=excess.deliveries_qty,
        sales_qty=excess.sales_qty,
        excess_qty=excess.excess_qty,
        excess_pct=excess.excess_pct,
        sold_out_dates=excess.sold_out_dates,
    )


@router.get("/movements", response_model=Page[StockMovementOut])
def list_movements(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("order.read"))],
    location: str | None = Query(default=None),
    item: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    cursor: str | None = Query(default=None, description="movement_id of the last row seen"),
    limit: int = Query(default=50, le=200),
) -> Page[StockMovementOut]:
    """Cursor-paginated, newest first. movement_id is a single global
    BIGSERIAL sequence shared across every partition, so it stays a valid,
    monotonic cursor even though the underlying table is partitioned by
    business_date.
    """
    stmt = select(StockMovement).order_by(StockMovement.movement_id.desc())
    if location:
        stmt = stmt.where(StockMovement.location_code == location)
    if item:
        stmt = stmt.where(StockMovement.item_code == item)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    if cursor:
        stmt = stmt.where(StockMovement.movement_id < int(cursor))

    rows = session.execute(stmt.limit(limit + 1)).scalars().all()
    next_cursor = str(rows[limit - 1].movement_id) if len(rows) > limit else None
    return Page(
        items=[StockMovementOut.model_validate(r) for r in rows[:limit]], next_cursor=next_cursor
    )


@router.post("/movements", response_model=StockMovementOut, status_code=201)
def create_manual_adjustment(
    body: ManualAdjustmentRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("movement.adjust"))],
) -> StockMovement:
    """A manual correction to the ledger. Always COUNT_ADJUSTMENT — never
    UPDATE/DELETE an existing row (the ledger is append-only; a mistake is
    corrected by an offsetting movement, not by editing history).
    """
    try:
        return write_movement(
            session,
            business_date=body.business_date,
            location_code=body.location_code,
            item_code=body.item_code,
            movement_type="COUNT_ADJUSTMENT",
            qty=body.qty,
            uom=body.uom,
            reason_code=body.reason_code,
            ref_doc_type="MANUAL",
            created_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
