"""
JWT creation and verification using python-jose.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from api.settings import settings


def create_access_token(user_id: str, email: str) -> str:
    """Sign and return a JWT for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Verify and decode a JWT. Raises jose.ExpiredSignatureError or
    jose.JWTError on failure — callers handle these.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
