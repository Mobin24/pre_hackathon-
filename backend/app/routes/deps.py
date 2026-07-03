"""Reusable FastAPI dependencies."""
from typing import Any, Dict

from app.core.security import decode_token
from app.core.db import get_database
from app.models import user as user_model
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


async def get_current_user(
    request: Request, token: str = Depends(oauth2_scheme)
) -> Dict[str, Any]:
    """Decode JWT → fetch user from Mongo → return **public** shape with string `id`."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"success": False, "error": "Invalid or expired credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except Exception:  # noqa: BLE001
        raise credentials_exc
    user_id = payload.sub
    if not user_id:
        raise credentials_exc
    raw = await user_model.find_by_id(user_id)
    if not raw:
        raise credentials_exc
    return user_model._serialize(raw)  # noqa: SLF001 — has id/name/email/role


async def require_db() -> bool:
    """503 if Mongo isn't configured. Used by all DB-backed endpoints."""
    try:
        get_database()
        return True
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": "Database not configured"},
        )
