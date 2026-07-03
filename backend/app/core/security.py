"""Password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import get_settings


# tokenUrl is the Swagger UI "Authorize" entry point. It does not need to be
# the exact path we use for login; we use OAuth2PasswordBearer's standard form.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=True)


class TokenPayload(BaseModel):
    sub: str  # user_id
    role: str
    exp: int


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison via bcrypt."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, role: str, expires_minutes: Optional[int] = None) -> str:
    """Issue a signed JWT carrying user_id (sub) and role."""
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.token_expiry_minutes
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    """Decode + validate a JWT. Raises 401 on any failure."""
    settings = get_settings()
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(sub=data["sub"], role=data["role"], exp=data["exp"])
    except (JWTError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency: extract the authenticated user's id from the bearer token."""
    payload = decode_token(token)
    return payload.sub