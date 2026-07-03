"""Pydantic schemas for authentication endpoints."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


Role = Literal["citizen", "admin"]


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = "citizen"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserPublic(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Role
    created_at: str
    updated_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserPublic