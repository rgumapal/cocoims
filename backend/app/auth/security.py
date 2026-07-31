"""Password hashing and JWT issuance/verification.

Pure functions only — no DB access here, so app.core.db and app.auth.security
have no dependency on each other and can be imported in either order.
"""
import datetime as dt

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int, token_type: str, expires_delta: dt.timedelta) -> str:
    """token_type is 'access' or 'refresh', checked by decode_token's caller
    so a refresh token can never be used where an access token is required
    (and vice versa) — the two must not be interchangeable."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, object]:
    """Raises jwt.PyJWTError (expired, malformed, bad signature) — callers
    are responsible for turning that into an HTTP 401."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
