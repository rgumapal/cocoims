"""User administration — SPEC §13: users, role assignment, branch scoping.

user.manage and role.manage are SYS_ADMIN-only in the seeded permission
matrix (SPEC §7.3) — there is no broader "read your own team" permission
yet, so every endpoint here is gated the same way the backend routes for
Reference Data are.

Multi-branch coverage (an Area Head across several areas, an OM covering
two branches during a vacancy) is exactly what core.user_scope already
supports: a user can hold several scope rows of any type (LOCATION | AREA
| CLUSTER | ROUTE | ALL), and effective scope is their union (SPEC §7.1
footnote, §7.2). This router exposes assign/revoke on that table directly
— no new scope model, the schema already generalizes to this case.
"""
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.deps import get_db, require_permission
from app.models import AppUser, Role, UserRole, UserScope

router = APIRouter(prefix="/api/v1", tags=["users"])

USER_MANAGE = "user.manage"
ROLE_MANAGE = "role.manage"


class UserOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    is_active: bool
    is_service: bool
    last_login_at: dt.datetime | None
    role_hint: str | None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    full_name: str
    is_active: bool = True
    is_service: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


class UserRoleOut(BaseModel):
    role_code: str
    granted_at: dt.datetime | None

    model_config = {"from_attributes": True}


class UserScopeOut(BaseModel):
    scope_id: int
    scope_type: str
    scope_value: str

    model_config = {"from_attributes": True}


class UserDetail(UserOut):
    roles: list[UserRoleOut]
    scopes: list[UserScopeOut]


class RoleAssignRequest(BaseModel):
    role_code: str


class ScopeAssignRequest(BaseModel):
    scope_type: str  # LOCATION | AREA | CLUSTER | ROUTE | ALL
    scope_value: str  # a code (e.g. 'AREA_QC') — ignored/'*' when scope_type='ALL'


class RoleOut(BaseModel):
    role_code: str
    label: str
    description: str | None
    is_system: bool

    model_config = {"from_attributes": True}


def _get_user_or_404(session: Session, user_id: int) -> AppUser:
    user = session.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> list[AppUser]:
    return list(session.execute(select(AppUser).order_by(AppUser.email)).scalars().all())


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> AppUser:
    """Creates the identity only — no password. Every seeded account is
    SSO-first (password_hash NULL); setting a local password is a separate,
    deliberately manual step (see backend/scripts/set_dev_passwords.py's
    docstring for why that script is dev-only).
    """
    existing = session.execute(select(AppUser).where(AppUser.email == body.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"{body.email} already exists")
    new_user = AppUser(**body.model_dump(), created_by=user.user_id)
    session.add(new_user)
    session.flush()
    return new_user


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> AppUser:
    user = session.execute(
        select(AppUser)
        .options(selectinload(AppUser.roles), selectinload(AppUser.scopes))
        .where(AppUser.user_id == user_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> AppUser:
    """is_active=False is how a user is deactivated (SPEC §5.6: Soft —
    deactivate; audit references must survive). There is no delete route.
    """
    target = _get_user_or_404(session, user_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    session.flush()
    return target


@router.post("/users/{user_id}/roles", response_model=UserRoleOut, status_code=201)
def assign_role(
    user_id: int,
    body: RoleAssignRequest,
    session: Annotated[Session, Depends(get_db)],
    actor: Annotated[AppUser, Depends(require_permission(ROLE_MANAGE))],
) -> UserRole:
    _get_user_or_404(session, user_id)
    if session.get(Role, body.role_code) is None:
        raise HTTPException(status_code=404, detail=f"Role {body.role_code} not found")
    if session.get(UserRole, (user_id, body.role_code)) is not None:
        raise HTTPException(status_code=409, detail="User already holds this role")
    grant = UserRole(user_id=user_id, role_code=body.role_code, granted_by=actor.user_id)
    session.add(grant)
    session.flush()
    return grant


@router.delete("/users/{user_id}/roles/{role_code}", status_code=204)
def revoke_role(
    user_id: int,
    role_code: str,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(ROLE_MANAGE))],
) -> None:
    grant = session.get(UserRole, (user_id, role_code))
    if grant is None:
        raise HTTPException(status_code=404, detail="User does not hold this role")
    session.delete(grant)
    session.flush()


@router.post("/users/{user_id}/scopes", response_model=UserScopeOut, status_code=201)
def assign_scope(
    user_id: int,
    body: ScopeAssignRequest,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> UserScope:
    """A user can hold several scope rows — this is what lets an Area Head
    cover several areas, or an OM cover two branches during a vacancy
    (SPEC §7.1 footnote): effective scope is the union of every row here,
    plus any location.om_user_id assignment, resolved live by
    app.auth.deps.resolve_effective_scope — never cached or duplicated.
    """
    _get_user_or_404(session, user_id)
    grant = UserScope(user_id=user_id, scope_type=body.scope_type, scope_value=body.scope_value)
    session.add(grant)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="This scope is already granted") from exc
    return grant


@router.delete("/users/{user_id}/scopes/{scope_id}", status_code=204)
def revoke_scope(
    user_id: int,
    scope_id: int,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> None:
    grant = session.get(UserScope, scope_id)
    if grant is None or grant.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scope grant not found")
    session.delete(grant)
    session.flush()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission(USER_MANAGE))],
) -> list[Role]:
    """Read-only list for the role-assignment dropdown. Creating new roles
    or editing what permissions a role grants (role.manage's other half)
    isn't built here — the seeded role set (SPEC §7.1) is fixed for now,
    same as every enum-backed dropdown elsewhere in this UI.
    """
    return list(session.execute(select(Role).order_by(Role.role_code)).scalars().all())
