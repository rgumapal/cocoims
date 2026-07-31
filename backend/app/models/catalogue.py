"""Item master and its supporting reference data.

Mirrors db/ddl/001_schema.sql §4.3 (independent lookups + item block) and
the item_price extensions from alembic/versions/0002_item_price_location_scope.py.

is_orderable and search_vector on Item are GENERATED ALWAYS columns — never
assign them from application code; Postgres computes and stores them, and
rejects an explicit value in the same INSERT/UPDATE that touches them.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    item_status_enum,
    item_type_enum,
    packaging_type_enum,
    replen_policy_enum,
)


class ItemCategory(Base):
    __tablename__ = "item_category"
    __table_args__ = {"schema": "core"}

    category_code: Mapped[str] = mapped_column(primary_key=True)
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("core.item_category.category_code"))
    label: Mapped[str]
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)


class Uom(Base):
    __tablename__ = "uom"
    __table_args__ = {"schema": "core"}

    uom_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    is_fractional: Mapped[bool] = mapped_column(default=False)


class ReasonCode(Base):
    __tablename__ = "reason_code"
    __table_args__ = {"schema": "core"}

    reason_code: Mapped[str] = mapped_column(primary_key=True)
    category: Mapped[str]  # OVERRIDE | WASTE | ADJUSTMENT
    label: Mapped[str]
    requires_note: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(default=True)


class SourceSystem(Base):
    __tablename__ = "source_system"
    __table_args__ = {"schema": "core"}

    source_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    system_type: Mapped[str]  # POS | ERP | FILE | API | AGGREGATOR
    is_active: Mapped[bool] = mapped_column(default=True)


class Item(Base):
    __tablename__ = "item"
    __table_args__ = (
        CheckConstraint(
            "(replen_policy = 'MULTI_DAY' AND shelf_life_days > 0) OR (replen_policy <> 'MULTI_DAY')",
            name="chk_policy_shelf",
        ),
        {"schema": "core"},
    )

    item_code: Mapped[str] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(item_type_enum)
    desc_dr: Mapped[str]  # name on Delivery Receipt — do not rename, ingestion matches this vocabulary
    desc_offtake: Mapped[str | None]  # name in sales system
    display_name: Mapped[str]
    category_code: Mapped[str | None] = mapped_column(ForeignKey("core.item_category.category_code"))
    base_uom: Mapped[str] = mapped_column(default="pc")
    packaging: Mapped[str] = mapped_column(packaging_type_enum, default="NA")
    shelf_life_days: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0 = same-day
    replen_policy: Mapped[str] = mapped_column(replen_policy_enum)
    moq: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    moq_exempt: Mapped[bool] = mapped_column(default=False)
    order_multiple: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), default=1)
    lifecycle_status: Mapped[str] = mapped_column(item_status_enum, default="ACTIVE")
    status_remark: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[dt.date | None]

    # GENERATED ALWAYS AS (...) STORED in Postgres. Computed() tells
    # SQLAlchemy to exclude these from every INSERT/UPDATE it issues —
    # without it, an unset nullable column is still sent as an explicit
    # NULL, which Postgres rejects for a generated column.
    is_orderable: Mapped[bool] = mapped_column(
        Computed("lifecycle_status IN ('ACTIVE','PILOT')")
    )
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(display_name,'') || ' ' || item_code)")
    )

    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    # No DB trigger refreshes this on UPDATE (verified against db/ddl/001_schema.sql)
    # — service code must set it explicitly on every update, the server_default
    # here only ever fires on INSERT.
    updated_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())

    aliases: Mapped[list["ItemAlias"]] = relationship(back_populates="item")
    prices: Mapped[list["ItemPrice"]] = relationship(back_populates="item")


class ItemAlias(Base):
    """DR and Offtake systems name the same item differently — this table
    resolves an inbound alias_text back to item_code during ingestion."""

    __tablename__ = "item_alias"
    __table_args__ = {"schema": "core"}

    alias_id: Mapped[int] = mapped_column(primary_key=True)
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"))
    source_code: Mapped[str] = mapped_column(ForeignKey("core.source_system.source_code"))
    alias_text: Mapped[str]

    item: Mapped["Item"] = relationship(back_populates="aliases")


class UomConversion(Base):
    __tablename__ = "uom_conversion"
    __table_args__ = {"schema": "core"}

    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"), primary_key=True)
    from_uom: Mapped[str] = mapped_column(primary_key=True)
    to_uom: Mapped[str] = mapped_column(primary_key=True)
    factor: Mapped[Decimal] = mapped_column(Numeric(14, 6))


class ItemPrice(Base):
    """Effective-dated price/cost. location_code NULL = network price;
    a non-null row is a branch override and takes precedence — application
    code should read core.v_effective_price rather than resolving that
    fallback itself. See alembic/versions/0002_item_price_location_scope.py
    and SPEC §4.3."""

    __tablename__ = "item_price"
    __table_args__ = {"schema": "core"}

    price_id: Mapped[int] = mapped_column(primary_key=True)
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"))
    location_code: Mapped[str | None] = mapped_column(ForeignKey("core.location.location_code"))
    srp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    price_status: Mapped[str] = mapped_column(default="CONFIRMED")  # CONFIRMED | PENDING_REVIEW | SUPERSEDED
    effective_from: Mapped[dt.date]
    effective_to: Mapped[dt.date | None]
    note: Mapped[str | None] = mapped_column(Text)

    item: Mapped["Item"] = relationship(back_populates="prices")
