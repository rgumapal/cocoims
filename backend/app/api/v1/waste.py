"""Waste recording — SPEC §13 POST /api/v1/waste.

qty in the request is the positive amount wasted (how a person naturally
describes it — "6 units expired"); write_movement requires WASTE rows to
carry a negative qty (SPEC §4.4's signed convention), so this negates it
once here rather than asking every caller to remember to pass a negative
number for what reads, in the UI, as a positive count of wasted units.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.stock import StockMovementOut
from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item, StockMovement

router = APIRouter(prefix="/api/v1/waste", tags=["waste"])

# Marks a correction posted by reverse_waste below, so is_reversed can find
# it later without guessing at a shape shared with any other correction
# idiom in the ledger (receiving's own corrections use a different
# ref_doc_type, "RECEIVING_CORRECTION" — see receiving.py).
_REVERSAL_REF_DOC_TYPE = "WASTE_REVERSAL"


class WasteEntryOut(BaseModel):
    movement_id: int
    business_date: dt.date
    item_code: str
    qty: Decimal  # positive — the amount wasted, same convention as WasteRequest
    reason_code: str | None
    production_date: dt.date | None
    created_by: int | None
    created_by_full_name: str | None
    created_at: dt.datetime | None
    is_reversed: bool


class WasteRequest(BaseModel):
    business_date: dt.date
    location_code: str
    item_code: str
    qty: Decimal  # positive — the amount wasted
    reason_code: str  # required (SPEC §7.4: no waste entry without a reason)
    production_date: dt.date | None = None  # which batch this depleted, for FEFO ageing

    @field_validator("qty")
    @classmethod
    def _qty_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("qty must be positive — the amount wasted, not a signed ledger delta")
        return v


@router.get("", response_model=list[WasteEntryOut])
def list_waste(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("waste.record"))],
    location_code: str = Query(...),
    business_date: dt.date = Query(...),
    item_code: str | None = Query(default=None),
) -> list[WasteEntryOut]:
    """What's already on file for one branch/date — lets the Waste Log
    screen show every item already reported for that day, in one table,
    before a new entry is made. item_code narrows to one item when given;
    omitted, this is the whole day's waste for the branch, which is what
    the main screen actually shows (SPEC: an editable table, not a
    one-item-at-a-time lookup).

    Multiple entries for the same (branch, item, date) are legitimate (a
    spoiled batch and a separately damaged one, different reasons) so this
    returns every original WASTE row, not a single net figure the way
    receiving's GET does — waste isn't a running total to reconcile, each
    entry is its own fact. is_reversed tells the caller whether a given
    entry's effect has already been undone by reverse_waste below, rather
    than the caller having to notice a same-day offsetting adjustment
    itself.
    """
    conditions = [
        StockMovement.location_code == location_code,
        StockMovement.business_date == business_date,
        StockMovement.movement_type == "WASTE",
    ]
    if item_code is not None:
        conditions.append(StockMovement.item_code == item_code)

    rows = session.execute(
        select(StockMovement, AppUser.full_name)
        .outerjoin(AppUser, AppUser.user_id == StockMovement.created_by)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
    ).all()
    if not rows:
        return []

    reversed_ids = set(
        session.execute(
            select(StockMovement.ref_doc_id).where(
                StockMovement.ref_doc_type == _REVERSAL_REF_DOC_TYPE,
                StockMovement.ref_doc_id.in_([str(m.movement_id) for m, _ in rows]),
            )
        ).scalars().all()
    )
    return [
        WasteEntryOut(
            movement_id=movement.movement_id,
            business_date=movement.business_date,
            item_code=movement.item_code,
            qty=-movement.qty,
            reason_code=movement.reason_code,
            production_date=movement.production_date,
            created_by=movement.created_by,
            created_by_full_name=full_name,
            created_at=movement.created_at,
            is_reversed=str(movement.movement_id) in reversed_ids,
        )
        for movement, full_name in rows
    ]


@router.post("", response_model=StockMovementOut, status_code=201)
def record_waste(
    body: WasteRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("waste.record"))],
) -> StockMovement:
    item = session.get(Item, body.item_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {body.item_code} not found")

    try:
        movement = write_movement(
            session,
            business_date=body.business_date,
            location_code=body.location_code,
            item_code=body.item_code,
            movement_type="WASTE",
            qty=-body.qty,
            uom=item.base_uom,
            reason_code=body.reason_code,
            production_date=body.production_date,
            ref_doc_type="WASTE",
            created_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return movement


@router.post("/{movement_id}/reverse", response_model=StockMovementOut, status_code=201)
def reverse_waste(
    movement_id: int,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("waste.record"))],
) -> StockMovement:
    """Corrects a mis-logged waste entry. Never an UPDATE or DELETE on the
    append-only ledger (CLAUDE.md DATA) — posts an offsetting
    COUNT_ADJUSTMENT for the original entry's full quantity instead, the
    same correction idiom app/api/v1/receiving.py already uses for its own
    corrections. The original WASTE row is untouched and stays on the
    ledger permanently; only the net effect on the branch's balance is
    undone.

    Gated on waste.record generally, not on having created the original
    entry yourself — no other permission in this app is scoped by "did you
    personally write this row" (see e.g. counts.py's approval check, which
    is the one place that distinction matters, and even there it's the
    opposite direction: blocking the *same* person, not requiring them).
    A shift lead correcting a team member's mis-entry is a normal case,
    not an edge one.
    """
    original = session.execute(
        select(StockMovement).where(
            StockMovement.movement_id == movement_id, StockMovement.movement_type == "WASTE"
        )
    ).scalar_one_or_none()
    if original is None:
        raise HTTPException(status_code=404, detail=f"Waste entry {movement_id} not found")

    already_reversed = session.execute(
        select(StockMovement).where(
            StockMovement.ref_doc_type == _REVERSAL_REF_DOC_TYPE,
            StockMovement.ref_doc_id == str(movement_id),
        )
    ).scalar_one_or_none()
    if already_reversed is not None:
        raise HTTPException(status_code=409, detail="This waste entry has already been reversed")

    return write_movement(
        session,
        business_date=original.business_date,
        location_code=original.location_code,
        item_code=original.item_code,
        movement_type="COUNT_ADJUSTMENT",
        qty=-original.qty,  # original.qty is negative; this is its positive counterpart
        uom=original.uom,
        reason_code="CORRECTION",
        production_date=original.production_date,
        ref_doc_type=_REVERSAL_REF_DOC_TYPE,
        ref_doc_id=str(movement_id),
        created_by=user.user_id,
    )
