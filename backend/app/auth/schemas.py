"""Request/response models for the auth endpoints (SPEC §13)."""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    """What GET /auth/me returns: the caller's identity plus their flattened
    permissions and effective branch scope — what the frontend needs to
    decide what to render, without re-deriving it client-side."""

    user_id: int
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]
    location_scope: list[str]
    unrestricted: bool
