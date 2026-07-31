"""Branch-to-branch transfers — SPEC §13 POST /api/v1/transfers.

Writes the TRANSFER_OUT / TRANSFER_IN pair atomically: both movements are
flushed in the same get_db transaction, so either both land or (on any
error) neither does — there is no state where stock left one branch's
ledger without arriving in the other's.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationInfo, field_validator
from sqlalchemy.orm import Session

from app.api.v1.stock import StockMovementOut
from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


class TransferRequest(BaseModel):
    business_date: dt.date
    from_location_code: str
    to_location_code: str
    item_code: str
    qty: Decimal  # positive — the amount transferred
    production_date: dt.date | None = None  # which batch this depleted, for FEFO ageing

    @field_validator("qty")
    @classmethod
    def _qty_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("qty must be positive — the amount transferred")
        return v

    @field_validator("to_location_code")
    @classmethod
    def _locations_must_differ(cls, v: str, info: ValidationInfo) -> str:
        from_loc = info.data.get("from_location_code")
        if from_loc is not None and v == from_loc:
            raise ValueError("from_location_code and to_location_code must differ")
        return v


class TransferResponse(BaseModel):
    transfer_out: StockMovementOut
    transfer_in: StockMovementOut


@router.post("", response_model=TransferResponse, status_code=201)
def create_transfer(
    body: TransferRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("movement.adjust"))],
) -> TransferResponse:
    item = session.get(Item, body.item_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {body.item_code} not found")

    try:
        transfer_out = write_movement(
            session,
            business_date=body.business_date,
            location_code=body.from_location_code,
            item_code=body.item_code,
            movement_type="TRANSFER_OUT",
            qty=-body.qty,
            uom=item.base_uom,
            production_date=body.production_date,
            counterparty_location=body.to_location_code,
            ref_doc_type="TRANSFER",
            created_by=user.user_id,
        )
        transfer_in = write_movement(
            session,
            business_date=body.business_date,
            location_code=body.to_location_code,
            item_code=body.item_code,
            movement_type="TRANSFER_IN",
            qty=body.qty,
            uom=item.base_uom,
            production_date=body.production_date,
            counterparty_location=body.from_location_code,
            ref_doc_type="TRANSFER",
            created_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransferResponse(
        transfer_out=StockMovementOut.model_validate(transfer_out),
        transfer_in=StockMovementOut.model_validate(transfer_in),
    )
