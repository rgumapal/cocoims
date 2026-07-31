"""ORM models mirroring the hand-authored schema in db/ddl and db/seed.

These describe an already-existing database; they never generate one
(Base.metadata is never passed to create_all/drop_all — see base.py).
"""
from app.models.base import Base
from app.models.catalogue import (
    Item,
    ItemAlias,
    ItemCategory,
    ItemPrice,
    ReasonCode,
    SourceSystem,
    Uom,
    UomConversion,
)
from app.models.identity import (
    ApiKey,
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
    UserScope,
)
from app.models.ledger import CountLine, CountSession, SoldOutEvent, StockMovement
from app.models.location import (
    Area,
    Cluster,
    Geography,
    Location,
    LocationClosure,
    LocationStatusHistory,
    Route,
)

__all__ = [
    "Base",
    "Item",
    "ItemAlias",
    "ItemCategory",
    "ItemPrice",
    "ReasonCode",
    "SourceSystem",
    "Uom",
    "UomConversion",
    "ApiKey",
    "AppUser",
    "Permission",
    "Role",
    "RolePermission",
    "UserRole",
    "UserScope",
    "CountLine",
    "CountSession",
    "SoldOutEvent",
    "StockMovement",
    "Area",
    "Cluster",
    "Geography",
    "Location",
    "LocationClosure",
    "LocationStatusHistory",
    "Route",
]
