"""Sales (offtake) recording — SPEC §1's "Sold"/"Offtake" glossary term.

One call covers one branch/day, one or more item lines — mirrors
app.api.v1.receiving's shape, since end-of-day sales entry is naturally
multi-item the same way a delivery is. qty in each line is the positive
amount sold; write_movement requires SALE rows to carry a negative qty
(SPEC §4.4's signed convention), negated once here for the same reason
app.api.v1.waste negates waste qty.

A line's sold_out flag writes a core.sold_out_event row (migration 0010) —
the signal Stock Explorer's Run Outs indicator reads (see
app.domain.ledger.excess_summary). It is not itself a movement: running out
is a fact about the day, separate from how many units were sold before it
happened.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.stock import StockMovementOut
from app.auth.deps import get_db, require_permission
from app.domain.ledger import write_movement
from app.models import AppUser, Item, SoldOutEvent

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


class SalesLineIn(BaseModel):
    item_code: str
    qty: Decimal  # positive — the amount sold
    sold_out: bool = False  # ran out at some point on this business_date


class SalesRequest(BaseModel):
    business_date: dt.date
    location_code: str
    lines: list[SalesLineIn]


def _record_sold_out(session: Session, *, business_date: dt.date, location_code: str, item_code: str, created_by: int) -> None:
    """Idempotent insert — re-submitting the same day's sales form (a
    double-submitted form, the realistic duplicate here) must not raise on
    the (business_date, location_code, item_code) primary key.
    """
    existing = session.execute(
        select(SoldOutEvent).where(
            SoldOutEvent.business_date == business_date,
            SoldOutEvent.location_code == location_code,
            SoldOutEvent.item_code == item_code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        SoldOutEvent(
            business_date=business_date,
            location_code=location_code,
            item_code=item_code,
            created_by=created_by,
        )
    )


@router.post("", response_model=list[StockMovementOut], status_code=201)
def record_sales(
    body: SalesRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("sales.record"))],
) -> list[StockMovementOut]:
    if not body.lines:
        raise HTTPException(status_code=422, detail="At least one line is required")

    movements = []
    for line in body.lines:
        if line.qty <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"{line.item_code}: qty must be positive — the amount sold, not a signed ledger delta",
            )

        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")

        try:
            movement = write_movement(
                session,
                business_date=body.business_date,
                location_code=body.location_code,
                item_code=line.item_code,
                movement_type="SALE",
                qty=-line.qty,
                uom=item.base_uom,
                # "SALE", not "POS" — this is the manual daily-entry path
                # (SPEC §16 open item #4's POS/DR question is still
                # unresolved); ref_doc_type should say how the row actually
                # got here, mirroring waste.py's own ref_doc_type="WASTE".
                ref_doc_type="SALE",
                created_by=user.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{line.item_code}: {exc}") from exc
        movements.append(movement)

        if line.sold_out:
            _record_sold_out(
                session,
                business_date=body.business_date,
                location_code=body.location_code,
                item_code=line.item_code,
                created_by=user.user_id,
            )

    return [StockMovementOut.model_validate(m) for m in movements]
