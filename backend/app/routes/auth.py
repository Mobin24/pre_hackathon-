"""Auth endpoints: register, login, me."""
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.db import get_database
from app.core.security import (
    create_access_token,
    decode_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.models import user as user_model
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _require_db():
    """Dependency: 503 if Mongo is not configured. Keeps error semantics clean."""
    try:
        return get_database()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, _db=Depends(_require_db)) -> TokenResponse:
    try:
        doc = await user_model.create_user(
            name=body.name.strip(),
            email=str(body.email).lower(),
            password_hash=hash_password(body.password),
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    settings = get_settings()
    token = create_access_token(user_id=doc["id"], role=doc["role"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.token_expiry_minutes * 60,
        user=UserPublic(**doc),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, _db=Depends(_require_db)) -> TokenResponse:
    user = await user_model.find_by_email(str(body.email).lower())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    serialized = {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user["created_at"].isoformat() if hasattr(user["created_at"], "isoformat") else user["created_at"],
        "updated_at": user["updated_at"].isoformat() if hasattr(user["updated_at"], "isoformat") else user["updated_at"],
    }
    settings = get_settings()
    token = create_access_token(user_id=serialized["id"], role=serialized["role"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.token_expiry_minutes * 60,
        user=UserPublic(**serialized),
    )


@router.get("/me", response_model=UserPublic)
async def me(user_id: str = Depends(get_current_user_id)) -> UserPublic:
    # get_current_user_id already validated the token signature/expiry.
    # We re-fetch to make sure the user still exists and to read current role/name.
    user = await user_model.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return UserPublic(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user["role"],
        created_at=user["created_at"].isoformat(),
        updated_at=user["updated_at"].isoformat(),
    )


def require_role(role: str) -> Callable:
    """Dependency factory: enforce that the token's role matches."""

    async def _checker(token: str = Depends(_bearer_token)) -> str:
        payload = decode_token(token)
        if payload.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {role}",
            )
        return payload.sub

    return _checker


# Lightweight bearer for require_role — reuses decode_token without re-running
# the default OAuth2 scheme (which makes Swagger UI cleaner for role-gated ops).
from fastapi.security import OAuth2PasswordBearer as _OAuth2  # noqa: E402

_bearer_token = _OAuth2(tokenUrl="auth/login", auto_error=True)