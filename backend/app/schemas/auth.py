"""Pydantic schemas for authentication endpoints."""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# --- Patterns ---------------------------------------------------------------
# Bangladesh NID is exactly 13 digits (10-digit legacy variant is no longer issued).
BD_NID_REGEX = r"^\d{13}$"
BD_PHONE_REGEX = r"^\+?8801[3-9]\d{8}$|^01[3-9]\d{8}$"


# --- Register (public, citizen only) ---------------------------------------
class RegisterRequest(BaseModel):
    """Public citizen registration payload.

    The `role` field is intentionally NOT accepted here — every public
    registration creates a `citizen` account. Admins must be created out of
    band via the seed script (`backend/scripts/seed_admin.py`).
    """

    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    # Optional Bangladesh-specific identity fields. Stored when present.
    nid: Optional[str] = Field(default=None, pattern=BD_NID_REGEX)
    phone: Optional[str] = Field(default=None, pattern=BD_PHONE_REGEX)

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v

    @field_validator("nid", "phone")
    @classmethod
    def _strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


# --- Login ------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Single-field login. Accepts email, phone, or BD NID as identifier."""

    identifier: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def _strip_identifier(cls, v: str) -> str:
        return v.strip()


# --- Public user shape -----------------------------------------------------
class UserPublic(BaseModel):
    """Safe, displayable user object — never includes the password hash."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    full_name: Optional[str] = Field(default=None, alias="name")
    name: Optional[str] = Field(default=None)  # kept for backwards compat
    email: EmailStr
    nid: Optional[str] = None
    phone: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Token response ---------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserPublic