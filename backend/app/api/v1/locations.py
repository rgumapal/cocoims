"""Branch/location CRUD, lifecycle status transitions, OM assignment and
closures — SPEC §13, §5.

status is never written directly by a client-supplied field on the
Location itself: only change_location_status does that, and every call
also writes core.location_status_history (SPEC §5.1 — "status is never
overwritten silently").
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.pagination import Page
from app.auth.deps import get_db, require_permission
from app.models import AppUser, Location, LocationClosure, LocationStatusHistory

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


class LocationOut(BaseModel):
    location_code: str
    location_type: str
    location_name: str
    store_format: str | None
    cluster_code: str | None
    area_code: str | None
    route_code: str | None
    om_user_id: int | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    geo_code: str | None
    status: str
    planned_open_date: dt.date | None
    open_date: dt.date | None
    close_date: dt.date | None
    ramp_weeks: int
    display_capacity_units: int | None
    parent_location_code: str | None
    relocated_to: str | None
    is_active: bool
    is_orderable: bool

    model_config = {"from_attributes": True}


class LocationCreate(BaseModel):
    location_code: str
    location_type: str
    location_name: str
    store_format: str | None = None
    cluster_code: str | None = None
    area_code: str | None = None
    route_code: str | None = None
    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    geo_code: str | None = None
    planned_open_date: dt.date | None = None
    ramp_weeks: int = 8
    display_capacity_units: int | None = None
    parent_location_code: str | None = None


class LocationUpdate(BaseModel):
    """PATCH semantics — status is deliberately excluded; use POST
    /{code}/status, which also writes the required history row."""

    location_name: str | None = None
    store_format: str | None = None
    cluster_code: str | None = None
    area_code: str | None = None
    route_code: str | None = None
    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    geo_code: str | None = None
    planned_open_date: dt.date | None = None
    open_date: dt.date | None = None
    close_date: dt.date | None = None
    ramp_weeks: int | None = None
    display_capacity_units: int | None = None
    parent_location_code: str | None = None
    relocated_to: str | None = None


class StatusChangeRequest(BaseModel):
    to_status: str
    reason_code: str | None = None
    note: str | None = None
    effective_from: dt.date | None = None  # defaults to today


class AssignOmRequest(BaseModel):
    om_user_id: int


class LocationStatusHistoryOut(BaseModel):
    history_id: int
    location_code: str
    from_status: str | None
    to_status: str
    effective_from: dt.date
    effective_to: dt.date | None
    reason_code: str | None
    note: str | None
    changed_by: int | None
    changed_at: dt.datetime | None

    model_config = {"from_attributes": True}


class LocationClosureOut(BaseModel):
    closure_id: int
    location_code: str
    start_date: dt.date
    end_date: dt.date
    closure_type: str
    is_full_day: bool
    exclude_from_forecast: bool
    note: str | None

    model_config = {"from_attributes": True}


class LocationClosureCreate(BaseModel):
    start_date: dt.date
    end_date: dt.date
    closure_type: str
    is_full_day: bool = True
    exclude_from_forecast: bool = True
    note: str | None = None


def _get_location_or_404(session: Session, location_code: str) -> Location:
    location = session.get(Location, location_code)
    if location is None:
        raise HTTPException(status_code=404, detail=f"Location {location_code} not found")
    return location


@router.get("", response_model=Page[LocationOut])
def list_locations(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.read"))],
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> Page[LocationOut]:
    stmt = select(Location).order_by(Location.location_code)
    if status:
        stmt = stmt.where(Location.status == status)
    if cursor:
        stmt = stmt.where(Location.location_code > cursor)

    rows = session.execute(stmt.limit(limit + 1)).scalars().all()
    next_cursor = rows[limit - 1].location_code if len(rows) > limit else None
    return Page(items=[LocationOut.model_validate(r) for r in rows[:limit]], next_cursor=next_cursor)


@router.post("", response_model=LocationOut, status_code=201)
def create_location(
    body: LocationCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.create"))],
) -> Location:
    if session.get(Location, body.location_code) is not None:
        raise HTTPException(status_code=409, detail=f"Location {body.location_code} already exists")
    location = Location(**body.model_dump())
    session.add(location)
    session.flush()
    # NUMERIC(9,6) columns (latitude, longitude) are stored at a fixed
    # scale regardless of the client's input precision — see items.py's
    # create_item for the general reason this matters.
    session.refresh(location)
    return location


@router.get("/{location_code}", response_model=LocationOut)
def get_location(
    location_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.read"))],
) -> Location:
    return _get_location_or_404(session, location_code)


@router.patch("/{location_code}", response_model=LocationOut)
def update_location(
    location_code: str,
    body: LocationUpdate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.update"))],
) -> Location:
    location = _get_location_or_404(session, location_code)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(location, field, value)
    location.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    session.refresh(location)  # NUMERIC scale — see create_location's comment
    return location


@router.post("/{location_code}/status", response_model=LocationOut)
def change_location_status(
    location_code: str,
    body: StatusChangeRequest,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("location.status_change"))],
) -> Location:
    """Lifecycle transition (SPEC §5.1). Closes any currently-open history
    row for this location before inserting the new one — both would
    otherwise carry effective_to IS NULL (i.e. open-ended ranges), which
    the EXCLUDE constraint on location_status_history correctly rejects as
    an overlap.
    """
    location = _get_location_or_404(session, location_code)
    effective_from = body.effective_from or dt.date.today()

    session.execute(
        update(LocationStatusHistory)
        .where(
            LocationStatusHistory.location_code == location_code,
            LocationStatusHistory.effective_to.is_(None),
        )
        .values(effective_to=effective_from)
    )
    session.add(
        LocationStatusHistory(
            location_code=location_code,
            from_status=location.status,
            to_status=body.to_status,
            effective_from=effective_from,
            reason_code=body.reason_code,
            note=body.note,
            changed_by=user.user_id,
        )
    )
    location.status = body.to_status
    location.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return location


@router.get("/{location_code}/status-history", response_model=list[LocationStatusHistoryOut])
def get_location_status_history(
    location_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.read"))],
) -> list[LocationStatusHistory]:
    _get_location_or_404(session, location_code)
    return list(
        session.execute(
            select(LocationStatusHistory)
            .where(LocationStatusHistory.location_code == location_code)
            .order_by(LocationStatusHistory.effective_from.desc())
        )
        .scalars()
        .all()
    )


@router.post("/{location_code}/assign-om", response_model=LocationOut)
def assign_om(
    location_code: str,
    body: AssignOmRequest,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.assign_om"))],
) -> Location:
    """Sets location.om_user_id. Grants branch scope immediately: scope is
    resolved live from this column on every request (app.auth.deps.
    resolve_effective_scope via core.v_user_effective_scope), so there is no
    second step and no stale grant when an OM changes (SPEC §7.2 rule 2).
    """
    location = _get_location_or_404(session, location_code)
    if session.get(AppUser, body.om_user_id) is None:
        raise HTTPException(status_code=404, detail=f"User {body.om_user_id} not found")
    location.om_user_id = body.om_user_id
    location.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return location


@router.get("/{location_code}/closures", response_model=list[LocationClosureOut])
def list_closures(
    location_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("location.closure.manage"))],
) -> list[LocationClosure]:
    _get_location_or_404(session, location_code)
    return list(
        session.execute(
            select(LocationClosure)
            .where(LocationClosure.location_code == location_code)
            .order_by(LocationClosure.start_date.desc())
        )
        .scalars()
        .all()
    )


@router.post("/{location_code}/closures", response_model=LocationClosureOut, status_code=201)
def create_closure(
    location_code: str,
    body: LocationClosureCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission("location.closure.manage"))],
) -> LocationClosure:
    """A closed day is an ABSENCE, not a zero (SPEC §5.3, CLAUDE.md
    BRANCHES) — exclude_from_forecast defaults True for exactly this
    reason. Concession-host cascade (parent_location_code) is forecast-side
    logic, not written here.
    """
    _get_location_or_404(session, location_code)
    closure = LocationClosure(
        location_code=location_code, created_by=user.user_id, **body.model_dump()
    )
    session.add(closure)
    session.flush()
    return closure
