"""Authentication and user schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.infrastructure.database.models import UserRole


class LoginRequest(BaseModel):
    """Credentials for the login endpoint."""

    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    email: EmailStr
    password: str = Field(min_length=8, description="Min 8 characters")
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = UserRole.client

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserUpdate(BaseModel):
    """Payload for updating an existing user."""

    full_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


class UserResponse(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PasswordChange(BaseModel):
    """Payload for changing the current user's password."""

    current_password: str
    new_password: str = Field(min_length=8)


class ProfileUpdate(BaseModel):
    """Правка собственного профиля.

    Роль и адрес почты здесь не меняются: это вопрос доступа,
    а не личных настроек.
    """

    full_name: Optional[str] = Field(default=None, max_length=255)
    preferred_name: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Как обращаться к пользователю",
    )
