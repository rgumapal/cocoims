"""Audit trail — mirrors db/ddl/001_schema.sql §4.9.

Read-only from the application's side: every row here is written by
audit.fn_capture(), a SECURITY DEFINER trigger function (see that
migration's own docstring) — cocoims_app only ever has SELECT on this
schema (migration 0004). No Python code should attempt to INSERT/UPDATE/
DELETE through this model; there is no route that does.
"""
import datetime as dt
import uuid

from sqlalchemy import ARRAY, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditRecordChange(Base):
    """One row per INSERT/UPDATE/DELETE on an audited table (core.item,
    core.location, core.transfer, ...). changed_by_email is denormalised
    on the row itself specifically so it survives deletion of the user it
    refers to — read that, not a live join, when the actor might no
    longer exist."""

    __tablename__ = "record_change"
    __table_args__ = {"schema": "audit"}

    # Composite PK (occurred_at, audit_id): RANGE partitioned on
    # occurred_at (SPEC §6.1), same partitioning shape as StockMovement.
    occurred_at: Mapped[dt.datetime] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    schema_name: Mapped[str]
    table_name: Mapped[str]
    record_pk: Mapped[str]
    action: Mapped[str]  # audit_action enum — plain str is fine, this model never writes
    changed_by: Mapped[int | None]
    changed_by_email: Mapped[str | None]
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    changed_fields: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    request_id: Mapped[uuid.UUID | None]
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
