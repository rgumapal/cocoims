"""Reference-data CRUD — SPEC §5.6/§5.7: every reference table gets full
create/read/update/deactivate in the UI, never a database console, never a
hard delete where history depends on the row.

Six tables (item_category, uom, cluster, area, route, reason_code) share
one shape exactly: a string code primary key, a handful of descriptive
columns, and is_active for soft-deactivation — the rule of three is well
past satisfied, so register_code_table_crud generates all five routes
(list/create/get/update/deactivate) once and every table below is a single
call naming its own model and schemas.

uom_conversion doesn't fit that shape (composite key, no is_active — SPEC
§5.6 gives it "Hard if unused" instead of soft-deactivate) and is wired up
separately, below the factory calls.

Every one of these is gated on refdata.manage: that is the only permission
code SPEC §7.3's seeded matrix defines for this resource — there is no
separate refdata.read. Narrower read access for more roles is a genuine
RBAC change (new permission code, new grants), not something to invent
silently here.
"""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import get_db, require_permission
from app.models import AppUser, Area, Cluster, Item, ItemCategory, ReasonCode, Route, Uom, UomConversion
from app.models.base import Base

router = APIRouter(prefix="/api/v1", tags=["refdata"])

REFDATA_PERMISSION = "refdata.manage"


def register_code_table_crud(
    *,
    path: str,
    model: type[Base],
    pk_field: str,
    out_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
) -> None:
    def _get_or_404(session: Session, code: str) -> Base:
        obj = session.get(model, code)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"{path}/{code} not found")
        return obj

    @router.get(f"/{path}", response_model=list[out_schema], name=f"list_{path}")  # type: ignore[valid-type]
    def list_(
        session: Annotated[Session, Depends(get_db)],
        _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
    ) -> list[Base]:
        return list(session.execute(select(model).order_by(getattr(model, pk_field))).scalars().all())

    @router.post(f"/{path}", response_model=out_schema, status_code=201, name=f"create_{path}")
    def create_(
        body: create_schema,  # type: ignore[valid-type]
        session: Annotated[Session, Depends(get_db)],
        _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
    ) -> Base:
        pk_value = getattr(body, pk_field)
        if session.get(model, pk_value) is not None:
            raise HTTPException(status_code=409, detail=f"{path}/{pk_value} already exists")
        obj = model(**body.model_dump())  # type: ignore[call-arg,attr-defined]
        session.add(obj)
        session.flush()
        return obj

    @router.get(f"/{path}/{{code}}", response_model=out_schema, name=f"get_{path}")
    def get_(
        code: str,
        session: Annotated[Session, Depends(get_db)],
        _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
    ) -> Base:
        return _get_or_404(session, code)

    @router.patch(f"/{path}/{{code}}", response_model=out_schema, name=f"update_{path}")
    def update_(
        code: str,
        body: update_schema,  # type: ignore[valid-type]
        session: Annotated[Session, Depends(get_db)],
        _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
    ) -> Base:
        obj = _get_or_404(session, code)
        for field, value in body.model_dump(exclude_unset=True).items():  # type: ignore[attr-defined]
            setattr(obj, field, value)
        session.flush()
        return obj

    @router.post(f"/{path}/{{code}}/deactivate", response_model=out_schema, name=f"deactivate_{path}")
    def deactivate_(
        code: str,
        session: Annotated[Session, Depends(get_db)],
        _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
    ) -> Base:
        obj = _get_or_404(session, code)
        obj.is_active = False  # type: ignore[attr-defined]
        session.flush()
        return obj


# ---------------------------------------------------------------------
# core.item_category
# ---------------------------------------------------------------------
class ItemCategoryOut(BaseModel):
    category_code: str
    parent_code: str | None
    label: str
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ItemCategoryCreate(BaseModel):
    category_code: str
    parent_code: str | None = None
    label: str
    sort_order: int = 0


class ItemCategoryUpdate(BaseModel):
    parent_code: str | None = None
    label: str | None = None
    sort_order: int | None = None


register_code_table_crud(
    path="categories",
    model=ItemCategory,
    pk_field="category_code",
    out_schema=ItemCategoryOut,
    create_schema=ItemCategoryCreate,
    update_schema=ItemCategoryUpdate,
)


# ---------------------------------------------------------------------
# core.uom
# ---------------------------------------------------------------------
class UomOut(BaseModel):
    uom_code: str
    label: str
    is_fractional: bool
    is_active: bool

    model_config = {"from_attributes": True}


class UomCreate(BaseModel):
    uom_code: str
    label: str
    is_fractional: bool = False


class UomUpdate(BaseModel):
    label: str | None = None
    is_fractional: bool | None = None


register_code_table_crud(
    path="uom",
    model=Uom,
    pk_field="uom_code",
    out_schema=UomOut,
    create_schema=UomCreate,
    update_schema=UomUpdate,
)


# ---------------------------------------------------------------------
# core.cluster
# ---------------------------------------------------------------------
class ClusterOut(BaseModel):
    cluster_code: str
    label: str
    description: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class ClusterCreate(BaseModel):
    cluster_code: str
    label: str
    description: str | None = None


class ClusterUpdate(BaseModel):
    label: str | None = None
    description: str | None = None


register_code_table_crud(
    path="clusters",
    model=Cluster,
    pk_field="cluster_code",
    out_schema=ClusterOut,
    create_schema=ClusterCreate,
    update_schema=ClusterUpdate,
)


# ---------------------------------------------------------------------
# core.area
# ---------------------------------------------------------------------
class AreaOut(BaseModel):
    area_code: str
    label: str
    is_active: bool

    model_config = {"from_attributes": True}


class AreaCreate(BaseModel):
    area_code: str
    label: str


class AreaUpdate(BaseModel):
    label: str | None = None


register_code_table_crud(
    path="areas",
    model=Area,
    pk_field="area_code",
    out_schema=AreaOut,
    create_schema=AreaCreate,
    update_schema=AreaUpdate,
)


# ---------------------------------------------------------------------
# core.route
# ---------------------------------------------------------------------
class RouteOut(BaseModel):
    route_code: str
    label: str
    dispatch_sequence: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class RouteCreate(BaseModel):
    route_code: str
    label: str
    dispatch_sequence: int | None = None


class RouteUpdate(BaseModel):
    label: str | None = None
    dispatch_sequence: int | None = None


register_code_table_crud(
    path="routes",
    model=Route,
    pk_field="route_code",
    out_schema=RouteOut,
    create_schema=RouteCreate,
    update_schema=RouteUpdate,
)


# ---------------------------------------------------------------------
# core.reason_code
# ---------------------------------------------------------------------
class ReasonCodeOut(BaseModel):
    reason_code: str
    category: str
    label: str
    requires_note: bool
    sort_order: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class ReasonCodeCreate(BaseModel):
    reason_code: str
    category: str  # OVERRIDE | WASTE | ADJUSTMENT
    label: str
    requires_note: bool = False
    sort_order: int | None = 0


class ReasonCodeUpdate(BaseModel):
    category: str | None = None
    label: str | None = None
    requires_note: bool | None = None
    sort_order: int | None = None


register_code_table_crud(
    path="reason-codes",
    model=ReasonCode,
    pk_field="reason_code",
    out_schema=ReasonCodeOut,
    create_schema=ReasonCodeCreate,
    update_schema=ReasonCodeUpdate,
)


# ---------------------------------------------------------------------
# core.uom_conversion — item-scoped, composite key, no is_active (SPEC
# §5.6: "Hard if unused"). Doesn't fit register_code_table_crud's shape.
# ---------------------------------------------------------------------
class UomConversionOut(BaseModel):
    item_code: str
    from_uom: str
    to_uom: str
    factor: Decimal

    model_config = {"from_attributes": True}


class UomConversionCreate(BaseModel):
    from_uom: str
    to_uom: str
    factor: Decimal


@router.get("/items/{item_code}/uom-conversions", response_model=list[UomConversionOut])
def list_uom_conversions(
    item_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
) -> list[UomConversion]:
    if session.get(Item, item_code) is None:
        raise HTTPException(status_code=404, detail=f"Item {item_code} not found")
    return list(
        session.execute(
            select(UomConversion).where(UomConversion.item_code == item_code)
        ).scalars().all()
    )


@router.post("/items/{item_code}/uom-conversions", response_model=UomConversionOut, status_code=201)
def create_uom_conversion(
    item_code: str,
    body: UomConversionCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
) -> UomConversion:
    if session.get(Item, item_code) is None:
        raise HTTPException(status_code=404, detail=f"Item {item_code} not found")
    conversion = UomConversion(item_code=item_code, **body.model_dump())
    session.add(conversion)
    session.flush()
    return conversion


@router.delete("/items/{item_code}/uom-conversions/{from_uom}/{to_uom}", status_code=204)
def delete_uom_conversion(
    item_code: str,
    from_uom: str,
    to_uom: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(REFDATA_PERMISSION))],
) -> None:
    """Hard delete (SPEC §5.6: "Hard if unused") — a conversion factor
    carries no history of its own, unlike the code tables above.
    """
    conversion = session.get(UomConversion, (item_code, from_uom, to_uom))
    if conversion is None:
        raise HTTPException(status_code=404, detail="Conversion not found")
    try:
        session.delete(conversion)
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Conversion is still in use") from exc
