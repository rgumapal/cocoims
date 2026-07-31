"""Item master CRUD, aliases and effective-dated prices — SPEC §13.

item.delete never removes a row: it sets lifecycle_status='DELISTED'
(CLAUDE.md BRANCHES / SPEC §5.6 — no hard delete on master data with
transactional history).
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.pagination import Page
from app.auth.deps import get_db, require_permission
from app.models import AppUser, Item, ItemAlias, ItemPrice

router = APIRouter(prefix="/api/v1/items", tags=["items"])


class ItemOut(BaseModel):
    item_code: str
    item_type: str
    desc_dr: str
    desc_offtake: str | None
    display_name: str
    category_code: str | None
    base_uom: str
    packaging: str
    shelf_life_days: int
    replen_policy: str
    moq: Decimal
    moq_exempt: bool
    order_multiple: Decimal | None
    lifecycle_status: str
    status_remark: str | None
    target_date: dt.date | None
    is_orderable: bool

    model_config = {"from_attributes": True}


class ItemCreate(BaseModel):
    item_code: str
    item_type: str
    desc_dr: str
    display_name: str
    replen_policy: str
    desc_offtake: str | None = None
    category_code: str | None = None
    base_uom: str = "pc"
    packaging: str = "NA"
    shelf_life_days: int = 0
    moq: Decimal = Decimal("0")
    moq_exempt: bool = False
    order_multiple: Decimal | None = Decimal("1")
    lifecycle_status: str = "ACTIVE"
    status_remark: str | None = None
    target_date: dt.date | None = None


class ItemUpdate(BaseModel):
    """All fields optional — PATCH semantics, only supplied fields change."""

    desc_dr: str | None = None
    desc_offtake: str | None = None
    display_name: str | None = None
    category_code: str | None = None
    base_uom: str | None = None
    packaging: str | None = None
    shelf_life_days: int | None = None
    replen_policy: str | None = None
    moq: Decimal | None = None
    moq_exempt: bool | None = None
    order_multiple: Decimal | None = None
    lifecycle_status: str | None = None
    status_remark: str | None = None
    target_date: dt.date | None = None


class ItemAliasOut(BaseModel):
    alias_id: int
    item_code: str
    source_code: str
    alias_text: str

    model_config = {"from_attributes": True}


class ItemAliasCreate(BaseModel):
    source_code: str
    alias_text: str


class ItemPriceOut(BaseModel):
    price_id: int
    item_code: str
    location_code: str | None
    srp: Decimal | None
    unit_cost: Decimal | None
    price_status: str
    effective_from: dt.date
    effective_to: dt.date | None
    note: str | None

    model_config = {"from_attributes": True}


class ItemPriceCreate(BaseModel):
    location_code: str | None = None  # NULL = network price (SPEC §4.3)
    srp: Decimal | None = None
    unit_cost: Decimal | None = None
    price_status: str = "CONFIRMED"
    effective_from: dt.date
    effective_to: dt.date | None = None
    note: str | None = None


def _get_item_or_404(session: Session, item_code: str) -> Item:
    item = session.get(Item, item_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_code} not found")
    return item


@router.get("", response_model=Page[ItemOut])
def list_items(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.read"))],
    search: str | None = Query(default=None, description="Full-text search over display_name + item_code"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> Page[ItemOut]:
    """Lists items, cursor-paginated by item_code. `search` matches SPEC
    §4.3's search_vector (idx_item_search) rather than a plain substring
    match, so misspellings and word order still find the right item.
    """
    stmt = select(Item).order_by(Item.item_code)
    if search:
        stmt = stmt.where(Item.search_vector.op("@@")(func.plainto_tsquery("simple", search)))
    if cursor:
        stmt = stmt.where(Item.item_code > cursor)

    rows = session.execute(stmt.limit(limit + 1)).scalars().all()
    next_cursor = rows[limit - 1].item_code if len(rows) > limit else None
    return Page(items=[ItemOut.model_validate(r) for r in rows[:limit]], next_cursor=next_cursor)


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    body: ItemCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.create"))],
) -> Item:
    if session.get(Item, body.item_code) is not None:
        raise HTTPException(status_code=409, detail=f"Item {body.item_code} already exists")
    item = Item(**body.model_dump())
    session.add(item)
    session.flush()
    # NUMERIC(12,3) columns (moq, order_multiple) are stored at a fixed
    # scale regardless of the client's input precision — without this, the
    # response would echo back e.g. moq=Decimal("12") instead of the
    # DB-stored Decimal("12.000").
    session.refresh(item)
    return item


@router.get("/{item_code}", response_model=ItemOut)
def get_item(
    item_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.read"))],
) -> Item:
    return _get_item_or_404(session, item_code)


@router.patch("/{item_code}", response_model=ItemOut)
def update_item(
    item_code: str,
    body: ItemUpdate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.update"))],
) -> Item:
    item = _get_item_or_404(session, item_code)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = dt.datetime.now(dt.timezone.utc)  # no DB trigger refreshes this — see models/catalogue.py
    session.flush()
    session.refresh(item)  # NUMERIC scale — see create_item's comment
    return item


@router.delete("/{item_code}", response_model=ItemOut)
def delist_item(
    item_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.delete"))],
) -> Item:
    """Never a real DELETE — sets lifecycle_status='DELISTED' so history
    (order lines, movements, prices) that reference this item stays valid.
    """
    item = _get_item_or_404(session, item_code)
    item.lifecycle_status = "DELISTED"
    item.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return item


@router.get("/{item_code}/aliases", response_model=list[ItemAliasOut])
def list_item_aliases(
    item_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.read"))],
) -> list[ItemAlias]:
    _get_item_or_404(session, item_code)
    return list(
        session.execute(select(ItemAlias).where(ItemAlias.item_code == item_code)).scalars().all()
    )


@router.post("/{item_code}/aliases", response_model=ItemAliasOut, status_code=201)
def create_item_alias(
    item_code: str,
    body: ItemAliasCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.update"))],
) -> ItemAlias:
    _get_item_or_404(session, item_code)
    alias = ItemAlias(item_code=item_code, **body.model_dump())
    session.add(alias)
    session.flush()
    return alias


@router.get("/{item_code}/prices", response_model=list[ItemPriceOut])
def list_item_prices(
    item_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.read"))],
) -> list[ItemPrice]:
    _get_item_or_404(session, item_code)
    return list(
        session.execute(
            select(ItemPrice)
            .where(ItemPrice.item_code == item_code)
            .order_by(ItemPrice.location_code.is_(None).desc(), ItemPrice.effective_from.desc())
        )
        .scalars()
        .all()
    )


@router.post("/{item_code}/prices", response_model=ItemPriceOut, status_code=201)
def create_item_price(
    item_code: str,
    body: ItemPriceCreate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("item.price.update"))],
) -> ItemPrice:
    """location_code NULL = network price; a non-null row is a branch
    override (SPEC §4.3). The EXCLUDE constraint on (item_code,
    location_code, daterange) rejects an overlapping effective range for
    the same item/location, surfaced here as a 409 rather than a raw
    Postgres exclusion-violation error.
    """
    _get_item_or_404(session, item_code)
    price = ItemPrice(item_code=item_code, **body.model_dump())
    session.add(price)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Overlapping effective date range for this item/location",
        ) from exc
    session.refresh(price)  # NUMERIC scale — see create_item's comment
    return price
