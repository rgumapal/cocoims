"""Shared declarative base and Postgres enum types for the ORM layer.

The schema is authored as plain SQL (db/ddl, db/seed, Alembic migrations) —
these models describe an already-existing database, they never generate one.
Base.metadata is never passed to `create_all`/`drop_all`; every enum below
is declared with `create_type=False` as a guard against that happening by
accident.
"""
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def pg_enum(*values: str, name: str) -> ENUM:
    """A Postgres enum already created by db/ddl/001_schema.sql §4.1.

    create_type=False/create_constraint=False: this ORM layer must never
    attempt to CREATE TYPE — the type already exists, owned by the DDL.
    """
    return ENUM(*values, name=name, schema=None, create_type=False, validate_strings=True)


item_type_enum = pg_enum(
    "FINISHED_GOOD", "SUPPLY", "PACKAGING", "RAW_MATERIAL", "INGREDIENT",
    name="item_type",
)
packaging_type_enum = pg_enum(
    "MANUAL_PACKING", "MACHINE_WRAPPED", "BULK", "NA",
    name="packaging_type",
)
item_status_enum = pg_enum(
    "ACTIVE", "PILOT", "TEMPORARILY_NOT_AVAILABLE", "DO_NOT_INCLUDE_YET", "DELISTED",
    name="item_status",
)
location_type_enum = pg_enum(
    "BRANCH", "COMMISSARY", "WAREHOUSE", "IN_TRANSIT", "VIRTUAL",
    name="location_type",
)
store_format_enum = pg_enum(
    "STANDALONE", "CONCESSION", "KIOSK",
    name="store_format",
)
location_status_enum = pg_enum(
    "PLANNED", "PRE_OPENING", "RAMP_UP", "ACTIVE",
    "TEMP_CLOSED", "RENOVATION", "RELOCATED", "CLOSED",
    name="location_status",
)
replen_policy_enum = pg_enum(
    "SAME_DAY", "MULTI_DAY", "MIN_MAX", "NONE",
    name="replen_policy",
)
movement_type_enum = pg_enum(
    "RECEIPT", "SALE", "WASTE", "TRANSFER_OUT", "TRANSFER_IN",
    "COUNT_ADJUSTMENT", "RETURN", "PRODUCTION", "CONSUMPTION", "OPENING",
    name="movement_type",
)
transfer_status_enum = pg_enum(
    "DRAFT", "IN_TRANSIT", "RECEIVED", "CANCELLED",
    name="transfer_status",
)
