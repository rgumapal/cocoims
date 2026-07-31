"""Authentication endpoints — SPEC §13:
POST /auth/login | refresh | logout, GET /auth/me.
"""
import datetime as dt

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_raw_session, resolve_effective_scope
from app.auth.schemas import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.auth.security import create_token, decode_token, verify_password
from app.core.config import settings
from app.models import AppUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _issue_pair(user_id: int) -> TokenResponse:
    return TokenResponse(
        access_token=create_token(
            user_id, "access", dt.timedelta(minutes=settings.jwt_access_token_minutes)
        ),
        refresh_token=create_token(
            user_id, "refresh", dt.timedelta(days=settings.jwt_refresh_token_days)
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_raw_session)) -> TokenResponse:
    """Authenticate with email + password, returning an access token
    (short-lived) and a refresh token.

    Requires: no permission — this is how a caller obtains one in the first
    place. Scope: none; this endpoint does not touch a scoped table.
    """
    user = session.execute(
        select(AppUser).where(AppUser.email == body.email)
    ).scalar_one_or_none()

    if user is None or user.password_hash is None or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    return _issue_pair(user.user_id)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, session: Session = Depends(get_raw_session)) -> TokenResponse:
    """Exchange a valid, unexpired refresh token for a new access + refresh
    token pair.

    Requires: no permission beyond holding a valid refresh token. A refresh
    token can never be used as an access token: decode_token round-trips the
    same secret for both, so the `type` claim is the only thing preventing
    that, and this endpoint checks it explicitly.
    """
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user = session.get(AppUser, int(str(payload["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return _issue_pair(user.user_id)


@router.post("/logout", status_code=204)
def logout(user: AppUser = Depends(get_current_user)) -> None:
    """Ends the caller's session.

    Requires: a valid access token. No server-side revocation list exists in
    this phase — JWTs are stateless, so this is advisory and the client must
    discard both tokens itself. A blocklist (e.g. in Redis, per SPEC §6.5)
    is the natural fast-follow if immediate server-side revocation becomes a
    real requirement; nothing in this phase depends on it, so it isn't built.
    """
    return None


@router.get("/me", response_model=MeResponse)
def me(
    user: AppUser = Depends(get_current_user),
    session: Session = Depends(get_raw_session),
) -> MeResponse:
    """Returns the caller's identity, flattened permissions and effective
    branch scope — what the frontend uses to decide what to render.

    Requires: a valid access token. No permission beyond being authenticated.
    """
    permissions = sorted(
        {
            row[0]
            for row in session.execute(
                text(
                    "SELECT DISTINCT rp.permission_code FROM core.user_role ur "
                    "JOIN core.role_permission rp ON rp.role_code = ur.role_code "
                    "WHERE ur.user_id = :uid"
                ),
                {"uid": user.user_id},
            ).all()
        }
    )
    unrestricted, location_scope = resolve_effective_scope(session, user.user_id)

    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        roles=[ur.role_code for ur in user.roles],
        permissions=permissions,
        location_scope=location_scope,
        unrestricted=unrestricted,
    )
