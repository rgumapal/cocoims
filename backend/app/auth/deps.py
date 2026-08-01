"""Authentication, permission and scope enforcement — the request-context
dependencies every protected endpoint composes.

Two layers, deliberately separate and both mandatory (SPEC §7.4 rule 2:
"neither substitutes for the other"):

- require_permission(code) is the API-layer check — deny by default, 403 on
  absence.
- get_db resolves the same user's branch scope and binds it to the database
  transaction (app.core.db.apply_session_context), which is what makes the
  RLS policies from migration 0004 actually see the caller's scope.

get_db additionally IS the guard from CLAUDE.md ACCESS ("a write without
session context is a bug"): it requires Depends(get_current_user), so
FastAPI resolves and fails authentication before get_db's body ever runs —
there is no code path that reaches a writable session without an
authenticated user attached to it.
"""
import uuid
from collections.abc import Callable, Generator
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.auth.security import decode_token
from app.core.db import RequestContext, SessionLocal, apply_session_context, get_raw_session
from app.models import AppUser

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_raw_session),
) -> AppUser:
    """Decodes the bearer token and loads the AppUser it names.

    Uses get_raw_session, not get_db: app_user carries no RLS policy, and
    this must run *before* a user is known, so it cannot depend on the very
    thing (get_db) that needs this function's result to resolve scope.

    auto_error=False on the bearer scheme + the explicit check below: the
    default HTTPBearer raises 403 for a missing Authorization header, which
    conflates "not authenticated" with "authenticated but not permitted".
    SPEC §7.4 draws that line at 401 vs 403 (require_permission below is
    what actually returns 403), so a missing/absent token is handled here
    to keep the distinction real rather than accidental.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")

    user = session.execute(
        select(AppUser)
        .options(selectinload(AppUser.roles))  # avoids N+1 when callers read user.roles
        .where(AppUser.user_id == int(str(payload["sub"])))
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def resolve_effective_scope(session: Session, user_id: int) -> tuple[bool, list[str]]:
    """Returns (unrestricted, location_codes) for a user — the same shape
    apply_session_context's RequestContext needs and GET /auth/me reports.
    Shared by app.auth.deps.get_db and the /me route so the two can never
    silently disagree on what "effective scope" means.

    Queries core.user_scope and core.v_user_effective_scope directly, both
    unaffected by RLS (neither carries a policy), so this is safe to call
    before apply_session_context has been run on this transaction.
    """
    unrestricted = bool(
        session.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM core.user_scope "
                "WHERE user_id = :uid AND scope_type = 'ALL')"
            ),
            {"uid": user_id},
        ).scalar_one()
    )
    if unrestricted:
        return True, []

    location_codes = list(
        session.execute(
            text("SELECT location_code FROM core.v_user_effective_scope WHERE user_id = :uid"),
            {"uid": user_id},
        )
        .scalars()
        .all()
    )
    return False, location_codes


def get_user_permissions(session: Session, user_id: int) -> set[str]:
    """The caller's full flattened permission set — every permission_code
    granted through any role they hold. Shared by GET /auth/me and the
    dashboard summary endpoint (app/api/v1/dashboard.py), which needs to
    check several permissions per request and would otherwise repeat this
    query once per section (exactly the N+1 pattern CLAUDE.md forbids).
    """
    return {
        row[0]
        for row in session.execute(
            text(
                "SELECT DISTINCT rp.permission_code FROM core.user_role ur "
                "JOIN core.role_permission rp ON rp.role_code = ur.role_code "
                "WHERE ur.user_id = :uid"
            ),
            {"uid": user_id},
        ).all()
    }


def get_db(
    user: AppUser = Depends(get_current_user),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
) -> Generator[Session, None, None]:
    """The session every scoped read/write must use. Opens a transaction,
    resolves the caller's effective scope, binds it plus user identity and
    the request id to the transaction (app.core.db.apply_session_context),
    then yields — commit on success, rollback on any exception.
    """
    try:
        request_id = UUID(x_request_id) if x_request_id else uuid.uuid4()
    except ValueError:
        request_id = uuid.uuid4()

    session = SessionLocal()
    try:
        session.begin()
        unrestricted, location_scope = resolve_effective_scope(session, user.user_id)
        apply_session_context(
            session,
            RequestContext(
                user_id=user.user_id,
                user_email=user.email,
                request_id=request_id,
                location_scope=location_scope,
                unrestricted=unrestricted,
            ),
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_permission(permission_code: str) -> Callable[..., AppUser]:
    """FastAPI dependency factory: 403s unless the caller holds
    permission_code through any of their roles (SPEC §7.3/§7.4 — deny by
    default). Route it alongside get_db, not instead of it: this checks
    *authority*, get_db enforces *scope* — SPEC §7.4 rule 2 requires both.
    """

    def _check(
        user: AppUser = Depends(get_current_user),
        session: Session = Depends(get_raw_session),
    ) -> AppUser:
        granted = session.execute(
            text(
                "SELECT 1 FROM core.user_role ur "
                "JOIN core.role_permission rp ON rp.role_code = ur.role_code "
                "WHERE ur.user_id = :uid AND rp.permission_code = :perm LIMIT 1"
            ),
            {"uid": user.user_id, "perm": permission_code},
        ).first()
        if granted is None:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission_code}")
        return user

    return _check
