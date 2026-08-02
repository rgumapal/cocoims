"""Branch-to-branch transfers — docs/features/TRANSFERS_V1.md.

Replaces the earlier prototype endpoint (a single instantaneous
TRANSFER_OUT/TRANSFER_IN pair with no in-transit leg, no state machine, no
gates, and zero callers — see docs/CLEANUP_PLAN.md's NOT_SURE #1 and
docs/INTEGRITY_ASSESSMENT.md, both of which flagged it as built-but-never-
wired-to-a-UI). That contract is not preserved: nothing called it, and it
had the exact "stock vanishes while the rider is in traffic" bug the new
design's rule 2 exists to prevent.

RLS (migration 0016) already restricts every row here to transfers where
the caller has scope on the source *or* destination branch. The finer
rule — ship needs scope on the source specifically, receive needs scope
on the destination specifically — is enforced below, not in RLS, for the
same reason app/api/v1/counts.py's approve_count enforces separation of
duties in the service layer rather than trying to express it as a policy
predicate: it's the transition being attempted that decides which side
matters, and that's a business rule, not a row-visibility rule.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.v1.pagination import Page
from app.auth.deps import get_db, require_permission, resolve_effective_scope
from app.domain.transfer import (
    check_destination_stocked,
    check_same_day_only_same_date,
    check_source_stock,
    post_receive,
    post_ship,
    validate_transition,
)
from app.models import AppUser, Item, Transfer, TransferLine

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


class TransferLineIn(BaseModel):
    item_code: str
    qty_requested: Decimal


class TransferCreate(BaseModel):
    source_location_code: str
    dest_location_code: str
    reason_code: str | None = None
    notes: str | None = None
    lines: list[TransferLineIn]


class TransferLineOut(BaseModel):
    item_code: str
    qty_requested: Decimal
    qty_shipped: Decimal | None
    qty_received: Decimal | None
    variance_qty: Decimal | None
    variance_reason_code: str | None

    model_config = {"from_attributes": True}


class TransferOut(BaseModel):
    transfer_id: int
    transfer_no: str | None
    source_location_code: str
    dest_location_code: str
    status: str
    reason_code: str | None
    notes: str | None
    created_by: int | None
    created_at: dt.datetime | None
    shipped_at: dt.datetime | None
    received_at: dt.datetime | None
    cancelled_at: dt.datetime | None

    model_config = {"from_attributes": True}


class TransferDetail(TransferOut):
    lines: list[TransferLineOut]
    warnings: list[str] = []


class ShipLineIn(BaseModel):
    item_code: str
    qty_shipped: Decimal


class ShipRequest(BaseModel):
    business_date: dt.date
    lines: list[ShipLineIn]


class ReceiveLineIn(BaseModel):
    item_code: str
    qty_received: Decimal
    variance_reason_code: str | None = None


class ReceiveRequest(BaseModel):
    business_date: dt.date
    lines: list[ReceiveLineIn]


def _get_transfer_or_404(session: Session, transfer_id: int) -> Transfer:
    transfer = session.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found")
    return transfer


def _require_scope(session: Session, user: AppUser, location_code: str, action: str) -> None:
    """The ship-must-be-source / receive-must-be-destination rule RLS's
    coarser either-side policy doesn't express — see module docstring."""
    unrestricted, location_codes = resolve_effective_scope(session, user.user_id)
    if not unrestricted and location_code not in location_codes:
        raise HTTPException(
            status_code=403, detail=f"You do not have scope on {location_code}, required to {action}"
        )


def _to_detail(transfer: Transfer, lines: list[TransferLine], warnings: list[str] | None = None) -> TransferDetail:
    return TransferDetail(
        **TransferOut.model_validate(transfer).model_dump(),
        lines=[TransferLineOut.model_validate(line) for line in lines],
        warnings=warnings or [],
    )


def _get_lines(session: Session, transfer_id: int) -> list[TransferLine]:
    return list(
        session.execute(
            select(TransferLine).where(TransferLine.transfer_id == transfer_id).order_by(TransferLine.item_code)
        ).scalars().all()
    )


@router.get("", response_model=Page[TransferOut])
def list_transfers(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("transfer.read"))],
    status: str | None = None,
    location: str | None = None,
    direction: str | None = Query(default=None, pattern="^(inbound|outbound)$"),
    cursor: str | None = None,
    limit: int = 50,
) -> Page[TransferOut]:
    """Newest first. RLS already restricts rows to transfers where the
    caller has scope on the source or destination — `location`/`direction`
    below are additional filters on top of that, for the Inbound/Outbound
    tabs on the Transfers list screen.
    """
    stmt = select(Transfer).order_by(Transfer.transfer_id.desc())
    if status:
        stmt = stmt.where(Transfer.status == status)
    if location:
        if direction == "inbound":
            stmt = stmt.where(Transfer.dest_location_code == location)
        elif direction == "outbound":
            stmt = stmt.where(Transfer.source_location_code == location)
        else:
            stmt = stmt.where(
                or_(Transfer.source_location_code == location, Transfer.dest_location_code == location)
            )
    if cursor:
        stmt = stmt.where(Transfer.transfer_id < int(cursor))

    rows = session.execute(stmt.limit(limit + 1)).scalars().all()
    next_cursor = str(rows[limit - 1].transfer_id) if len(rows) > limit else None
    return Page(
        items=[TransferOut.model_validate(r) for r in rows[:limit]], next_cursor=next_cursor
    )


@router.post("", response_model=TransferDetail, status_code=201)
def create_transfer(
    body: TransferCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("transfer.create"))],
) -> TransferDetail:
    """Creates a DRAFT transfer with its lines. No ledger movement is
    posted yet — see rule 1 (ledger only, no mutable balance): a draft is
    just a plan, stock only actually moves at ship/receive. Runs gates 1
    and 2 up front so the creator sees the same warnings the Ship screen
    will show, before committing to the trip.
    """
    if body.source_location_code == body.dest_location_code:
        raise HTTPException(status_code=422, detail="source_location_code and dest_location_code must differ")
    if not body.lines:
        raise HTTPException(status_code=422, detail="At least one line is required")
    # Without this, an out-of-scope create would still be rejected — by
    # the scope_by_source_insert RLS policy — but as a raw, unhandled
    # Postgres error (500), not the clean 403 every other authority check
    # in this API returns. Same reasoning as _require_scope's other
    # callers below.
    _require_scope(session, user, body.source_location_code, "create a transfer from")

    warnings: list[str] = []
    for line in body.lines:
        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")
        w = check_source_stock(
            session,
            location_code=body.source_location_code,
            item_code=line.item_code,
            business_date=dt.date.today(),
            qty=line.qty_requested,
        )
        if w:
            warnings.append(w)
        w = check_destination_stocked(session, location_code=body.dest_location_code, item_code=line.item_code)
        if w:
            warnings.append(w)

    transfer = Transfer(
        source_location_code=body.source_location_code,
        dest_location_code=body.dest_location_code,
        reason_code=body.reason_code,
        notes=body.notes,
        created_by=user.user_id,
    )
    session.add(transfer)
    session.flush()  # populates transfer_id
    transfer.transfer_no = f"TRF-{transfer.transfer_id:06d}"

    lines = [
        TransferLine(
            transfer_id=transfer.transfer_id,
            item_code=line.item_code,
            source_location_code=body.source_location_code,
            dest_location_code=body.dest_location_code,
            qty_requested=line.qty_requested,
        )
        for line in body.lines
    ]
    session.add_all(lines)
    session.flush()

    return _to_detail(transfer, lines, warnings)


@router.get("/{transfer_id}", response_model=TransferDetail)
def get_transfer(
    transfer_id: int,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("transfer.read"))],
) -> TransferDetail:
    transfer = _get_transfer_or_404(session, transfer_id)
    return _to_detail(transfer, _get_lines(session, transfer_id))


@router.post("/{transfer_id}/ship", response_model=TransferDetail)
def ship_transfer(
    transfer_id: int,
    body: ShipRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("transfer.ship"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> TransferDetail:
    """Posts source -> in-transit for every line. A rider on bad signal
    double-tapping this with the same Idempotency-Key gets the same
    result back, not a second posting or an error (AC-5) — checked before
    the state-machine transition, so a genuine replay never even sees the
    "not DRAFT" error a second, different ship attempt on an already-
    shipped transfer correctly gets.
    """
    transfer = _get_transfer_or_404(session, transfer_id)

    if (
        transfer.status != "DRAFT"
        and idempotency_key is not None
        and transfer.ship_idempotency_key == idempotency_key
    ):
        return _to_detail(transfer, _get_lines(session, transfer_id))

    validate_transition_or_409(transfer.status, "IN_TRANSIT")
    _require_scope(session, user, transfer.source_location_code, "ship")

    if not body.lines:
        raise HTTPException(status_code=422, detail="At least one line is required")

    warnings: list[str] = []
    for line in body.lines:
        w = check_source_stock(
            session,
            location_code=transfer.source_location_code,
            item_code=line.item_code,
            business_date=body.business_date,
            qty=line.qty_shipped,
        )
        if w:
            warnings.append(w)

    try:
        post_ship(
            session,
            transfer=transfer,
            lines={line.item_code: line.qty_shipped for line in body.lines},
            business_date=body.business_date,
            created_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    transfer.status = "IN_TRANSIT"
    transfer.shipped_by = user.user_id
    transfer.shipped_at = dt.datetime.now(dt.timezone.utc)
    transfer.ship_idempotency_key = idempotency_key
    session.flush()

    return _to_detail(transfer, _get_lines(session, transfer_id), warnings)


@router.post("/{transfer_id}/receive", response_model=TransferDetail)
def receive_transfer(
    transfer_id: int,
    body: ReceiveRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("transfer.receive"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> TransferDetail:
    """Posts in-transit -> destination. Received qty is never defaulted
    from shipped (rule 4) — every line here is what the destination
    actually counted. A shortfall or overage requires
    variance_reason_code; the difference is posted against in-transit as
    an adjustment so that bucket always nets to zero (see
    app.domain.transfer.post_receive).
    """
    transfer = _get_transfer_or_404(session, transfer_id)

    if (
        transfer.status != "IN_TRANSIT"
        and idempotency_key is not None
        and transfer.receive_idempotency_key == idempotency_key
    ):
        return _to_detail(transfer, _get_lines(session, transfer_id))

    validate_transition_or_409(transfer.status, "RECEIVED")
    _require_scope(session, user, transfer.dest_location_code, "receive")

    if not body.lines:
        raise HTTPException(status_code=422, detail="At least one line is required")

    existing_lines = {line.item_code: line for line in _get_lines(session, transfer_id)}
    for line in body.lines:
        shipped_line = existing_lines.get(line.item_code)
        if shipped_line is None or shipped_line.qty_shipped is None:
            raise HTTPException(status_code=422, detail=f"{line.item_code} was never shipped on this transfer")
        if line.qty_received != shipped_line.qty_shipped and line.variance_reason_code is None:
            raise HTTPException(
                status_code=422,
                detail=f"{line.item_code}: variance_reason_code is required when received "
                f"({line.qty_received}) differs from shipped ({shipped_line.qty_shipped})",
            )
        item = session.get(Item, line.item_code)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {line.item_code} not found")
        try:
            check_same_day_only_same_date(
                session, transfer_no=transfer.transfer_no or str(transfer.transfer_id),
                item=item, receive_business_date=body.business_date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        post_receive(
            session,
            transfer=transfer,
            lines={
                line.item_code: (line.qty_received, line.variance_reason_code) for line in body.lines
            },
            business_date=body.business_date,
            created_by=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    transfer.status = "RECEIVED"
    transfer.received_by = user.user_id
    transfer.received_at = dt.datetime.now(dt.timezone.utc)
    transfer.receive_idempotency_key = idempotency_key
    session.flush()

    return _to_detail(transfer, _get_lines(session, transfer_id))


@router.post("/{transfer_id}/cancel", response_model=TransferDetail)
def cancel_transfer(
    transfer_id: int,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("transfer.cancel"))],
) -> TransferDetail:
    """Only valid before ship (the state machine only allows DRAFT ->
    CANCELLED) — after ship, the correction is a reverse transfer, per
    rule in docs/features/TRANSFERS_V1.md."""
    transfer = _get_transfer_or_404(session, transfer_id)
    validate_transition_or_409(transfer.status, "CANCELLED")
    _require_scope(session, user, transfer.source_location_code, "cancel")

    transfer.status = "CANCELLED"
    transfer.cancelled_by = user.user_id
    transfer.cancelled_at = dt.datetime.now(dt.timezone.utc)
    session.flush()

    return _to_detail(transfer, _get_lines(session, transfer_id))


def validate_transition_or_409(current_status: str, target_status: str) -> None:
    try:
        validate_transition(current_status, target_status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
