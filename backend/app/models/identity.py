"""Identity, RBAC and branch-scoping models.

Mirrors db/ddl/001_schema.sql §4.2. Authority = permission x branch scope
(CLAUDE.md ACCESS): AppUser holds Roles, which resolve to Permissions;
UserScope (plus Location.om_user_id, resolved separately via
core.v_user_effective_scope — never duplicated here) determines which
branches a user's permissions apply to.
"""
import datetime as dt

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = {"schema": "core"}

    user_id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str]
    password_hash: Mapped[str | None] = mapped_column(Text)  # NULL when SSO-only
    sso_subject: Mapped[str | None] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[dt.datetime | None]
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[dt.datetime | None]
    role_hint: Mapped[str | None]  # display-only, added by migration 0002 — never read for authz
    created_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    created_by: Mapped[int | None]

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")
    scopes: Mapped[list["UserScope"]] = relationship(back_populates="user")


class Role(Base):
    __tablename__ = "role"
    __table_args__ = {"schema": "core"}

    role_code: Mapped[str] = mapped_column(primary_key=True)
    label: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = {"schema": "core"}

    permission_code: Mapped[str] = mapped_column(primary_key=True)
    resource: Mapped[str]
    action: Mapped[str]
    label: Mapped[str]
    is_destructive: Mapped[bool] = mapped_column(Boolean, default=False)


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = {"schema": "core"}

    role_code: Mapped[str] = mapped_column(ForeignKey("core.role.role_code"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("core.permission.permission_code"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = {"schema": "core"}

    user_id: Mapped[int] = mapped_column(ForeignKey("core.app_user.user_id"), primary_key=True)
    role_code: Mapped[str] = mapped_column(ForeignKey("core.role.role_code"), primary_key=True)
    granted_at: Mapped[dt.datetime | None] = mapped_column(server_default=func.now())
    granted_by: Mapped[int | None]

    user: Mapped["AppUser"] = relationship(back_populates="roles")


class UserScope(Base):
    """Explicit scope grant. NOT the full effective scope on its own — a
    location's om_user_id also grants scope automatically (SPEC §7.2 rule 2)
    and is resolved separately via core.v_user_effective_scope, never
    duplicated into this table (CLAUDE.md ACCESS)."""

    __tablename__ = "user_scope"
    __table_args__ = {"schema": "core"}

    scope_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.app_user.user_id"))
    scope_type: Mapped[str]  # LOCATION | AREA | CLUSTER | ROUTE | ALL
    scope_value: Mapped[str]

    user: Mapped["AppUser"] = relationship(back_populates="scopes")


class ApiKey(Base):
    __tablename__ = "api_key"
    __table_args__ = {"schema": "core"}

    key_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("core.app_user.user_id"))
    key_hash: Mapped[str] = mapped_column(Text)
    key_prefix: Mapped[str]
    label: Mapped[str]
    scopes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    expires_at: Mapped[dt.datetime | None]
    revoked_at: Mapped[dt.datetime | None]
    last_used_at: Mapped[dt.datetime | None]
