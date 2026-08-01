"""Authentication endpoints — SPEC §13:
POST /auth/login | refresh | logout, GET /auth/me.
"""
import datetime as dt

import jwt
from fastapi import APIRouter, Depends, HTTPException
from firebase_admin.exceptions import FirebaseError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_raw_session, get_user_permissions, resolve_effective_scope
from app.auth.firebase import verify_firebase_id_token
from app.auth.schemas import FirebaseLoginRequest, LoginRequest, MeResponse, RefreshRequest, TokenResponse
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


@router.post("/firebase", response_model=TokenResponse)
def firebase_login(
    body: FirebaseLoginRequest, session: Session = Depends(get_raw_session)
) -> TokenResponse:
    """Authenticate via Firebase — the one identity provider this app uses,
    covering both Google sign-in and email+password (SPEC §16 open item
    #11). The ID token's own claims say which provider was actually used;
    this endpoint doesn't need to care which.

    Verifies the ID token's signature against Google's own certs (never
    trusted from the client as-is), then matches it to an *existing*
    core.app_user by email. Deliberately never auto-creates an account on
    first sign-in — provisioning stays an explicit admin action on the
    Users screen (which also provisions the Firebase credential itself,
    see app/auth/firebase.py's provision_firebase_credential), same as
    every other account in this system (CLAUDE.md ACCESS: deny by default).

    Requires: no permission — same bootstrapping role as /login.
    """
    try:
        decoded = verify_firebase_id_token(body.id_token)
    except (ValueError, FirebaseError) as exc:
        raise HTTPException(status_code=401, detail="Invalid sign-in") from exc

    email = decoded.get("email")
    if not email or not decoded.get("email_verified"):
        raise HTTPException(status_code=401, detail="Account has no verified email")

    user = session.execute(select(AppUser).where(AppUser.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=403,
            detail="No Cocopan IMS account for this email — ask an admin to create one first",
        )
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    if user.sso_subject is None:
        user.sso_subject = decoded["uid"]
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
    permissions = sorted(get_user_permissions(session, user.user_id))
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
