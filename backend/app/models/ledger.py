"""The stock ledger and physical counts.

Mirrors db/ddl/001_schema.sql §4.4 and §4.7. StockMovement is append-only —
enforced in the database (migration 0004: a trigger on every partition, plus
the app role's UPDATE/DELETE grants revoked), not just by convention here.
app.domain.ledger.write_movement is the only path application code should
use to create a row; never construct and add() a StockMovement anywhere
else, so the append-only/signed-qty rules stay in one place.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import Computed, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, movement_type_enum, transfer_status_enum


class StockMovement(Base):
    __tablename__ = "stock_movement"
    __table_args__ = {"schema": "core"}

    # Composite PK (business_date, movement_id): the table is RANGE
    # partitioned on business_date (SPEC §6.1), and Postgres requires a
    # partitioned table's primary key to include the partition key.
    # autoincrement explicit: SQLAlchemy only infers SERIAL/IDENTITY
    # semantics automatically for a single-column PK; a composite PK needs
    # this spelled out or it warns on every insert (movement_id is
    # BIGSERIAL in the DDL — Postgres supplies it either way, but this
    # keeps SQLAlchemy's own bookkeeping accurate).
    business_date: Mapped[dt.date] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    occurred_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"))
    movement_type: Mapped[str] = mapped_column(movement_type_enum)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))  # signed: +in, -out
    uom: Mapped[str]
    production_date: Mapped[dt.date | None]  # enables FEFO and ageing
    expiry_date: Mapped[dt.date | None]
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reason_code: Mapped[str | None] = mapped_column(ForeignKey("core.reason_code.reason_code"))
    ref_doc_type: Mapped[str | None]  # DR | ORDER | COUNT | POS | TRANSFER
    ref_doc_id: Mapped[str | None]
    counterparty_location: Mapped[str | None]  # for transfers
    source_code: Mapped[str | None] = mapped_column(ForeignKey("core.source_system.source_code"))
    idempotency_key: Mapped[str | None]
    created_by: Mapped[int | None]
    # Who physically handled this movement, if different from created_by
    # (the logged-in system account) — e.g. a shared branch tablet account
    # submitting on behalf of whoever actually received the delivery. Free
    # text, not a core.app_user FK: the physical handler isn't necessarily
    # a system user. Added by migration 0013.
    confirmed_by_name: Mapped[str | None]
    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())


class CountSession(Base):
    __tablename__ = "count_session"
    __table_args__ = {"schema": "core"}

    count_id: Mapped[int] = mapped_column(primary_key=True)
    location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    count_type: Mapped[str]  # DAILY_EI | CYCLE | FULL
    business_date: Mapped[dt.date]
    started_at: Mapped[dt.datetime | None]
    submitted_at: Mapped[dt.datetime | None]
    submitted_by: Mapped[int | None]
    approved_at: Mapped[dt.datetime | None]  # added by migration 0007
    approved_by: Mapped[int | None]  # added by migration 0007
    status: Mapped[str] = mapped_column(default="OPEN")


class CountLine(Base):
    """was_counted is not redundant with counted_qty: a branch that counted
    zero and a branch that skipped the item are different facts (CLAUDE.md
    DATA, SPEC §4.7). expected_qty must be populated server-side from
    app.domain.ledger.balance_as_of — never trust a client-supplied value,
    or the variance this table exists to surface becomes meaningless."""

    __tablename__ = "count_line"
    __table_args__ = {"schema": "core"}

    count_id: Mapped[int] = mapped_column(ForeignKey("core.count_session.count_id"), primary_key=True)
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"), primary_key=True)
    counted_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    expected_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    # GENERATED ALWAYS AS (...) STORED in Postgres — Computed() tells
    # SQLAlchemy to exclude this from every INSERT/UPDATE it issues; without
    # it, an unset nullable column is still sent as an explicit NULL, which
    # Postgres rejects for a generated column.
    variance_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), Computed("counted_qty - expected_qty")
    )

    variance_reason: Mapped[str | None]
    was_counted: Mapped[bool] = mapped_column(default=False)


class Transfer(Base):
    """Branch-to-branch rebalance — migration 0016, docs/features/TRANSFERS_V1.md.

    transfer_no is set application-side once transfer_id is known (the
    BIGSERIAL PK), not a DB default — see app.domain.transfer.create_transfer.
    ship_idempotency_key/receive_idempotency_key back true idempotent replay
    on those two actions (SPEC's general Idempotency-Key convention was
    never actually wired to a stored value anywhere else in this codebase
    before this feature — see app.domain.transfer for how it's checked).
    """

    __tablename__ = "transfer"
    __table_args__ = {"schema": "core"}

    transfer_id: Mapped[int] = mapped_column(primary_key=True)
    transfer_no: Mapped[str | None]
    source_location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    dest_location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    status: Mapped[str] = mapped_column(transfer_status_enum, default="DRAFT")
    reason_code: Mapped[str | None] = mapped_column(ForeignKey("core.reason_code.reason_code"))
    notes: Mapped[str | None]
    created_by: Mapped[int | None]
    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    shipped_by: Mapped[int | None]
    shipped_at: Mapped[dt.datetime | None]
    ship_idempotency_key: Mapped[str | None]
    received_by: Mapped[int | None]
    received_at: Mapped[dt.datetime | None]
    receive_idempotency_key: Mapped[str | None]
    cancelled_by: Mapped[int | None]
    cancelled_at: Mapped[dt.datetime | None]


class TransferLine(Base):
    """source_location_code/dest_location_code are denormalised from the
    parent Transfer at creation, never updated after — see migration
    0016's docstring for why (this table has no RLS-usable location column
    of its own otherwise, the same gap flagged for core.count_line in
    docs/INTEGRITY_ASSESSMENT.md's top-5 #3; denormalising avoids repeating
    it here). No audit trigger: composite PK, same exemption as
    role_permission/uom_conversion/item_location_param (001_schema.sql)."""

    __tablename__ = "transfer_line"
    __table_args__ = {"schema": "core"}

    transfer_id: Mapped[int] = mapped_column(ForeignKey("core.transfer.transfer_id"), primary_key=True)
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"), primary_key=True)
    source_location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    dest_location_code: Mapped[str] = mapped_column(ForeignKey("core.location.location_code"))
    qty_requested: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    qty_shipped: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    qty_received: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    variance_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), Computed("qty_received - qty_shipped")
    )
    variance_reason_code: Mapped[str | None] = mapped_column(ForeignKey("core.reason_code.reason_code"))


class SoldOutEvent(Base):
    """One row per (business_date, location, item) the branch ran out —
    added by migration 0010 as the signal the Run Outs metric needs. A fact
    about the day, not a quantity, so it lives outside stock_movement (see
    that migration's docstring for why)."""

    __tablename__ = "sold_out_event"
    __table_args__ = {"schema": "core"}

    business_date: Mapped[dt.date] = mapped_column(primary_key=True)
    location_code: Mapped[str] = mapped_column(
        ForeignKey("core.location.location_code"), primary_key=True
    )
    item_code: Mapped[str] = mapped_column(ForeignKey("core.item.item_code"), primary_key=True)
    created_by: Mapped[int | None]
    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
