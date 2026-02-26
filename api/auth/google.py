"""
Google OAuth helpers: build auth URL, exchange code, verify ID token.
"""
from __future__ import annotations

import time
from typing import Any, Dict
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, jwt as authlib_jwt
from fastapi import HTTPException

from api.settings import settings

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Module-level JWK cache
_jwk_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWK_TTL = 55 * 60  # 55 minutes


def build_auth_url(state: str) -> str:
    """Return the Google OAuth consent-screen URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for Google tokens. Raises HTTP 400 on failure."""
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange OAuth code with Google.")
    return resp.json()


async def _get_google_jwks() -> Any:
    """Return cached Google JWK key set, refreshing if stale."""
    now = time.monotonic()
    if _jwk_cache["keys"] is None or now - _jwk_cache["fetched_at"] > _JWK_TTL:
        async with httpx.AsyncClient() as client:
            resp = await client.get(_GOOGLE_CERTS_URL)
        resp.raise_for_status()
        _jwk_cache["keys"] = JsonWebKey.import_key_set(resp.json())
        _jwk_cache["fetched_at"] = now
    return _jwk_cache["keys"]


async def verify_id_token(id_token: str) -> dict:
    """
    Verify a Google ID token using Google's public JWK certs.
    Returns a dict with keys: sub, email, name, picture.
    Raises HTTP 400 on failure.
    """
    try:
        jwks = await _get_google_jwks()
        claims = authlib_jwt.decode(id_token, jwks)
        claims.validate()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Google ID token: {exc}") from exc

    return {
        "sub": claims["sub"],
        "email": claims.get("email", ""),
        "name": claims.get("name", ""),
        "picture": claims.get("picture", ""),
    }
