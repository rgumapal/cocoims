"""Delivery receiving — SPEC §13 POST /api/v1/receiving.

One call covers one delivery (one location, one business_date, one or more
item lines) — a DR (Delivery Receipt, per the domain glossary in SPEC §1)
is naturally multi-item, so this doesn't force one HTTP call per line.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.stock import StockMovementOut
from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item

router = APIRouter(prefix="/api/v1/receiving", tags=["receiving"])


class ReceivingLineIn(BaseModel):
    item_code: str
    qty: Decimal
    production_date: dt.date | None = None  # enables FEFO for MULTI_DAY items
    expiry_date: dt.date | None = None  # derived from item.shelf_life_days if omitted
    unit_cost: Decimal | None = None


class ReceivingRequest(BaseModel):
    business_date: dt.date
    location_code: str
    ref_doc_id: str | None = None  # DR number, if the client has one
    lines: list[ReceivingLineIn]


@router.post("", response_model=list[StockMovementOut], status_code=201)
def confirm_receiving(
    body: ReceivingRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("receiving.confirm"))],
) -> list[StockMovementOut]:
    if not body.lines:
        raise HTTPException(status_code=422, detail="At least one line is required")

    movements = []
    for line in body.lines:
        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")

        expiry_date = line.expiry_date
        if expiry_date is None and line.production_date is not None and item.shelf_life_days > 0:
            expiry_date = line.production_date + dt.timedelta(days=item.shelf_life_days)

        try:
            movement = write_movement(
                session,
                business_date=body.business_date,
                location_code=body.location_code,
                item_code=line.item_code,
                movement_type="RECEIPT",
                qty=line.qty,
                uom=item.base_uom,
                production_date=line.production_date,
                expiry_date=expiry_date,
                unit_cost=line.unit_cost,
                ref_doc_type="DR",
                ref_doc_id=body.ref_doc_id,
                created_by=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{line.item_code}: {exc}") from exc
        movements.append(movement)

    return [StockMovementOut.model_validate(m) for m in movements]
