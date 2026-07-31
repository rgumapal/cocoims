"""Physical counts — SPEC §13, §4.7.

was_counted is not redundant with counted_qty (CLAUDE.md DATA): a branch
that counted zero and a branch that skipped the item are different facts,
and the request schema below keeps them distinct all the way through.
expected_qty is always populated server-side from the ledger, never
trusted from the client — otherwise the variance this table exists to
surface would be meaningless.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_db, require_permission
from app.core.config import settings
from app.domain.ledger import balance_as_of
from app.models import AppUser, CountLine, CountSession

router = APIRouter(prefix="/api/v1/counts", tags=["counts"])


class CountSessionOut(BaseModel):
    count_id: int
    location_code: str
    count_type: str
    business_date: dt.date
    started_at: dt.datetime | None
    submitted_at: dt.datetime | None
    submitted_by: int | None
    approved_at: dt.datetime | None
    approved_by: int | None
    status: str

    model_config = {"from_attributes": True}


class CountSessionCreate(BaseModel):
    location_code: str
    count_type: str  # DAILY_EI | CYCLE | FULL
    business_date: dt.date


class CountLineOut(BaseModel):
    count_id: int
    item_code: str
    counted_qty: Decimal | None
    expected_qty: Decimal | None
    variance_qty: Decimal | None
    variance_reason: str | None
    was_counted: bool

    model_config = {"from_attributes": True}


class CountLineIn(BaseModel):
    item_code: str
    counted_qty: Decimal | None = None
    was_counted: bool
    variance_reason: str | None = None


class CountSessionDetail(CountSessionOut):
    lines: list[CountLineOut]


def _get_session_or_404(session: Session, count_id: int) -> CountSession:
    count_session = session.get(CountSession, count_id)
    if count_session is None:
        raise HTTPException(status_code=404, detail=f"Count session {count_id} not found")
    return count_session


@router.post("", response_model=CountSessionOut, status_code=201)
def open_count(
    body: CountSessionCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("count.submit"))],
) -> CountSession:
    existing = session.execute(
        select(CountSession).where(
            CountSession.location_code == body.location_code,
            CountSession.count_type == body.count_type,
            CountSession.business_date == body.business_date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A {body.count_type} count for {body.location_code} on "
            f"{body.business_date} already exists (count_id={existing.count_id})",
        )

    count_session = CountSession(
        location_code=body.location_code,
        count_type=body.count_type,
        business_date=body.business_date,
        started_at=dt.datetime.now(dt.timezone.utc),
        status="OPEN",
    )
    session.add(count_session)
    session.flush()
    return count_session


@router.get("/{count_id}", response_model=CountSessionDetail)
def get_count(
    count_id: int,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("count.submit"))],
) -> CountSessionDetail:
    count_session = _get_session_or_404(session, count_id)
    lines = session.execute(
        select(CountLine).where(CountLine.count_id == count_id).order_by(CountLine.item_code)
    ).scalars().all()
    return CountSessionDetail(
        **CountSessionOut.model_validate(count_session).model_dump(),
        lines=[CountLineOut.model_validate(line) for line in lines],
    )


@router.post("/{count_id}/lines", response_model=list[CountLineOut])
def submit_count_lines(
    count_id: int,
    body: list[CountLineIn],
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("count.submit"))],
) -> list[CountLine]:
    """Upserts lines into an OPEN session — calling this again for an
    item_code already on the session updates it rather than duplicating
    (count_line's primary key is (count_id, item_code)).
    """
    count_session = _get_session_or_404(session, count_id)
    if count_session.status != "OPEN":
        raise HTTPException(
            status_code=409, detail=f"Count session {count_id} is {count_session.status}, not OPEN"
        )

    lines = []
    for line_in in body:
        expected_qty = balance_as_of(
            session, count_session.location_code, line_in.item_code, count_session.business_date
        )
        line = session.get(CountLine, (count_id, line_in.item_code))
        if line is None:
            line = CountLine(count_id=count_id, item_code=line_in.item_code)
            session.add(line)
        line.counted_qty = line_in.counted_qty
        line.expected_qty = expected_qty
        line.was_counted = line_in.was_counted
        line.variance_reason = line_in.variance_reason
        lines.append(line)

    session.flush()
    for line in lines:
        session.refresh(line)  # variance_qty is DB-generated — pick up the computed value
    return lines


@router.post("/{count_id}/submit", response_model=CountSessionOut)
def submit_count(
    count_id: int,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("count.submit"))],
) -> CountSession:
    count_session = _get_session_or_404(session, count_id)
    if count_session.status != "OPEN":
        raise HTTPException(
            status_code=409, detail=f"Count session {count_id} is {count_session.status}, not OPEN"
        )
    count_session.status = "SUBMITTED"
    count_session.submitted_at = dt.datetime.now(dt.timezone.utc)
    count_session.submitted_by = user.user_id
    session.flush()
    return count_session


@router.post("/{count_id}/approve", response_model=CountSessionOut)
def approve_count(
    count_id: int,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("count.approve"))],
) -> CountSession:
    """Separation of duties (SPEC §7.4): the user who submitted the count
    cannot also approve it if any line's variance exceeds
    settings.count_variance_approval_threshold. Enforced here, in the
    service layer, not left to the UI to hide the button.
    """
    count_session = _get_session_or_404(session, count_id)
    if count_session.status != "SUBMITTED":
        raise HTTPException(
            status_code=409,
            detail=f"Count session {count_id} is {count_session.status}, not SUBMITTED",
        )

    threshold = settings.count_variance_approval_threshold
    max_abs_variance = session.execute(
        select(func.max(func.abs(CountLine.variance_qty))).where(CountLine.count_id == count_id)
    ).scalar_one()
    exceeds_threshold = max_abs_variance is not None and max_abs_variance > threshold
    if exceeds_threshold and count_session.submitted_by == user.user_id:
        raise HTTPException(
            status_code=403,
            detail=(
                f"A variance over {threshold} units cannot be approved by the same "
                "user who submitted the count."
            ),
        )

    count_session.status = "APPROVED"
    count_session.approved_at = dt.datetime.now(dt.timezone.utc)
    count_session.approved_by = user.user_id
    session.flush()
    return count_session
