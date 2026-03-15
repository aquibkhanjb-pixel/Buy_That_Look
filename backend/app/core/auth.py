"""
JWT authentication for FastAPI.

Flow:
  1. NextAuth (frontend) calls POST /api/v1/users/sync after Google login.
  2. Backend creates/finds user, returns a signed access_token.
  3. Frontend stores token in NextAuth session (backendToken).
  4. Every subsequent API call sends: Authorization: Bearer <token>
  5. FastAPI dependency get_current_user() verifies and returns payload.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()

_ALGORITHM            = "HS256"
_ACCESS_TOKEN_DAYS    = 30
_security             = HTTPBearer(auto_error=True)


def create_access_token(user_id: str, email: str, tier: str) -> str:
    """Mint a signed JWT valid for 30 days."""
    expire = datetime.utcnow() + timedelta(days=_ACCESS_TOKEN_DAYS)
    payload = {
        "sub":   user_id,
        "email": email,
        "tier":  tier,
        "exp":   expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """FastAPI dependency — verifies Bearer token, returns decoded payload."""
    return _decode(credentials.credentials)


def require_premium(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that additionally enforces Premium tier."""
    if user.get("tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a Premium subscription.",
        )
    return user
