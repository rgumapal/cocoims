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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.v1.stock import StockMovementOut
from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item, StockMovement

router = APIRouter(prefix="/api/v1/waste", tags=["waste"])


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
