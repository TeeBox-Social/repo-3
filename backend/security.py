"""Auth & rate-limit primitives shared across routers.

Provides:
  * ``pwd_context``      — bcrypt password hashing/verify
  * ``limiter``          — proxy-aware SlowAPI limiter
  * ``get_current_user`` — FastAPI dep that resolves the JWT to a user document
  * ``create_access_token`` / ``create_refresh_token``
  * ``require_admin``    — helper that raises 403 when the user isn't admin
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import ACCESS_EXPIRE_MIN, ALGORITHM, REFRESH_EXPIRE_DAYS, SECRET_KEY, is_admin_user
from db import refresh_tokens_col, users_col
from helpers import now_iso


def _client_ip(request: Request) -> str:
    """Prefer the real client IP behind proxy/CDN over the socket peer."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=_client_ip)


def create_access_token(sub: str) -> str:
    payload = {
        "sub": sub,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_MIN),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def create_refresh_token(user_id: str, family_id: Optional[str] = None) -> str:
    jti = str(uuid.uuid4())
    family_id = family_id or jti
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)
    token = jwt.encode(
        {
            "sub": user_id,
            "type": "refresh",
            "jti": jti,
            "family_id": family_id,
            "exp": expires_at,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    await refresh_tokens_col.insert_one({
        "jti": jti,
        "user_id": user_id,
        "family_id": family_id,
        "expires_at": expires_at,
        "is_revoked": False,
        "is_rotated": False,
        "created_at": now_iso(),
    })
    return token


def create_typed_token(sub: str, token_type: str, expires_minutes: int) -> str:
    """Build a short-lived signed token for out-of-band flows (email verify,
    password reset). ``sub`` is the user id; ``token_type`` is asserted on
    consumption so an access token can't be used as a reset token and vice versa.
    """
    payload = {
        "sub": sub,
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_typed_token(token: str, expected_type: str) -> dict:
    """Decode a token and enforce the ``type`` claim. Raises HTTPException(400/401)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=400, detail="Invalid token type")
    return payload


async def get_current_user(cred: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if cred is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 30})
        if payload.get("type") not in (None, "access"):
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user: dict) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")
