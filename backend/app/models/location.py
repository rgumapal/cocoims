"""Branch/location master and lifecycle history.

Mirrors db/ddl/001_schema.sql §4.3. is_active and is_orderable are
GENERATED ALWAYS from status — never set by hand (CLAUDE.md BRANCHES).
Every status transition must also write a LocationStatusHistory row; the
service layer enforces this, not a trigger, so it can validate the
transition (SPEC §5.1) and require a reason in the same call.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, location_status_enum, location_type_enum, store_format_enum


class Area(Base):
    __tablename__ = "area"
    __table_args__ = {"schema": "core"}

    area_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)  # added by migration 0006


class Cluster(Base):
    """Forecast analog group (TRANSPORT_HUB, RESIDENTIAL,
    SUPERMARKET_CONCESSION, HIGH_TRAFFIC_24H, ...) — SPEC §5.5."""

    __tablename__ = "cluster"
    __table_args__ = {"schema": "core"}

    cluster_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)  # added by migration 0006


class Route(Base):
    __tablename__ = "route"
    __table_args__ = {"schema": "core"}

    route_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    dispatch_sequence: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(default=True)  # added by migration 0006


class Geography(Base):
    """PH region/province/city/barangay hierarchy — SPEC §4.3."""

    __tablename__ = "geography"
    __table_args__ = {"schema": "core"}

    geo_code: Mapped[str] = mapped_column(primary_key=True)
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("core.geography.geo_code"))
    geo_level: Mapped[str]  # REGION | PROVINCE | CITY | BARANGAY
    label: Mapped[str]


class Location(Base):
    __tablename__ = "location"
    __table_args__ = {"schema": "core"}

    location_code: Mapped[str] = mapped_column(primary_key=True)
    location_type: Mapped[str] = mapped_column(location_type_enum)
    location_name: Mapped[str]
    store_format: Mapped[str | None] = mapped_column(store_format_enum)
    cluster_code: Mapped[str | None] = mapped_column(ForeignKey("core.cluster.cluster_code"))
    area_code: Mapped[str | None] = mapped_column(ForeignKey("core.area.area_code"))
    route_code: Mapped[str | None] = mapped_column(ForeignKey("core.route.route_code"))
    om_user_id: Mapped[int | None] = mapped_column(ForeignKey("core.app_user.user_id"))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    geo_code: Mapped[str | None] = mapped_column(ForeignKey("core.geography.geo_code"))
    status: Mapped[str] = mapped_column(location_status_enum, default="PLANNED")
    planned_open_date: Mapped[dt.date | None]
    open_date: Mapped[dt.date | None]
    close_date: Mapped[dt.date | None]
    ramp_weeks: Mapped[int] = mapped_column(SmallInteger, default=8)
    operating_hours: Mapped[dict | None] = mapped_column(JSONB)
    display_capacity_units: Mapped[int | None]
    parent_location_code: Mapped[str | None] = mapped_column(ForeignKey("core.location.location_code"))
    relocated_to: Mapped[str | None] = mapped_column(ForeignKey("core.location.location_code"))

    # GENERATED ALWAYS from status in Postgres. Computed() excludes these
    # from every INSERT/UPDATE SQLAlchemy issues — see catalogue.py's Item
    # for why this is required, not just documentation.
    is_active: Mapped[bool] = mapped_column(Computed("status IN ('RAMP_UP','ACTIVE')"))
    is_orderable: Mapped[bool] = mapped_column(
        Computed("status IN ('PRE_OPENING','RAMP_UP','ACTIVE')")
    )

    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    # No DB trigger refreshes this on UPDATE — service code sets it explicitly.
    updated_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())

    status_history: Mapped[list["LocationStatusHistory"]] = relationship(back_populates="location")
    closures: Mapped[list["LocationClosure"]] = relationship(back_populates="location")


class LocationStatusHistory(Base):
    """Full lifecycle trail. Never overwrite Location.status without writing
    a row here — forecasting depends on knowing what a branch WAS on any
    past date (SPEC §5.1). Append-only in practice; nothing in this phase
    updates or deletes a row here."""

    __tablename__ = "location_status_history"
    __table_args__ = {"schema": "core"}

    history_id: Mapped[int] = mapped_column(primary_key=True)
    location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    from_status: Mapped[str | None] = mapped_column(location_status_enum)
    to_status: Mapped[str] = mapped_column(location_status_enum)
    effective_from: Mapped[dt.date]
    effective_to: Mapped[dt.date | None]
    reason_code: Mapped[str | None]
    note: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None]
    changed_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())

    location: Mapped["Location"] = relationship(back_populates="status_history")


class LocationClosure(Base):
    """Day-level closure. exclude_from_forecast=true means these dates are
    an ABSENCE, not a zero — CRITICAL for the forecast reference window
    (SPEC §5.3, CLAUDE.md BRANCHES)."""

    __tablename__ = "location_closure"
    __table_args__ = (
        CheckConstraint("end_date >= start_date"),
        {"schema": "core"},
    )

    closure_id: Mapped[int] = mapped_column(primary_key=True)
    location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    start_date: Mapped[dt.date]
    end_date: Mapped[dt.date]
    closure_type: Mapped[str]  # HOLIDAY | RENOVATION | UTILITY | WEATHER | HOST_CLOSED | OTHER
    is_full_day: Mapped[bool] = mapped_column(default=True)
    exclude_from_forecast: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None]

    location: Mapped["Location"] = relationship(back_populates="closures")


class ItemLocationParam(Base):
    """Per-branch assortment: is_stocked, par/MOQ overrides, shelf capacity
    (SPEC §5.5, §5.6). No rows exist yet anywhere in this database — the
    onboarding wizard and assortment templates that would populate it
    aren't built (see docs/INTEGRITY_ASSESSMENT.md). Consumers must treat
    a missing row as "no assortment data recorded" (is_stocked unknown),
    never as "not stocked" — see app.domain.transfer's destination-stocks
    gate for the concrete case this matters for."""

    __tablename__ = "item_location_param"
    __table_args__ = {"schema": "core"}

    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"), primary_key=True)
    location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"), primary_key=True)
    is_stocked: Mapped[bool] = mapped_column(default=True)
    par_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    moq_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    display_capacity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    source_template: Mapped[str | None] = mapped_column(ForeignKey("core.assortment_template.template_code"))
    is_overridden: Mapped[bool] = mapped_column(default=False)
