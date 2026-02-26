"""
FastAPI dependency for authenticated routes.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import ExpiredSignatureError, JWTError

from api.auth.jwt import decode_access_token

_bearer = HTTPBearer()


async def get_current_user(credentials=Depends(_bearer)) -> dict:
    """Extract and verify the Bearer JWT. Returns the decoded payload."""
    try:
        return decode_access_token(credentials.credentials)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
