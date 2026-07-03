"""Auth endpoints.

Public surface:
- POST /auth/register   — create a citizen account (role hardcoded to "citizen")
- POST /auth/login      — sign in with email, phone, or BD NID
- GET  /auth/me         — current authenticated user

Admin accounts cannot be created through any HTTP endpoint. They must be
provisioned via the seeder at `backend/scripts/seed_admin.py`.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import user as user_model
from app.routes.deps import get_current_user, oauth2_scheme, require_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# --- Dependencies ----------------------------------------------------------
# `get_current_user` and `require_db` are shared in `app/routes/deps.py`.


def require_role(role: str):
    """Factory that returns a FastAPI dependency enforcing `user.role == role`."""
    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"success": False, "error": "Forbidden"},
            )
        return user
    return _checker


# --- Endpoints -------------------------------------------------------------
@router.post("/register", response_model=TokenResponse, status_code=201)
async def register_endpoint(
    payload: RegisterRequest,
    request: Request,
    _: bool = Depends(require_db),
) -> TokenResponse:
    """Citizen registration. Role is always set to `citizen` server-side."""
    try:
        user = await user_model.create_user(
            full_name=payload.full_name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role="citizen",  # hardcoded; never trusted from the client
            nid=payload.nid,
            phone=payload.phone,
        )
    except ValueError as exc:
        # Duplicate email/nid/phone → 409 with a copy-pastable message.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"success": False, "error": str(exc)},
        )

    settings = get_settings()
    token = create_access_token(
        user_id=user["id"], role=user["role"], expires_minutes=settings.token_expiry_minutes
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.token_expiry_minutes * 60,
        user=UserPublic(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            nid=user.get("nid"),
            phone=user.get("phone"),
            role=user["role"],
            created_at=user.get("created_at"),
            updated_at=user.get("updated_at"),
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(
    payload: LoginRequest,
    request: Request,
    _: bool = Depends(require_db),
) -> TokenResponse:
    """Sign in with email, phone, or BD NID. Same lookup for everyone; admins
    also use this endpoint — `role` is read from the DB after authentication.
    """
    user = await user_model.find_by_identifier(payload.identifier)
    if not user or not verify_password(payload.password, user["password_hash"]):
        # Generic error — never reveal which half was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"success": False, "error": "Invalid credentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    token = create_access_token(
        user_id=str(user["_id"]), role=user["role"], expires_minutes=settings.token_expiry_minutes
    )
    serialized = user_model._serialize(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.token_expiry_minutes * 60,
        user=UserPublic(
            id=serialized["id"],
            name=serialized["name"],
            email=serialized["email"],
            nid=serialized.get("nid"),
            phone=serialized.get("phone"),
            role=serialized["role"],
            created_at=serialized.get("created_at"),
            updated_at=serialized.get("updated_at"),
        ),
    )


@router.get("/me", response_model=UserPublic)
async def me_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> UserPublic:
    # `current_user` is already the serialized public shape (see deps.py).
    return UserPublic(**current_user)


# --- Helpers ---------------------------------------------------------------
# (no helper functions currently needed; keep this section for future utils)