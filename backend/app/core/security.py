"""JWT token creation/verification, password hashing, and auth dependency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt_lib
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database.session import get_session

# Password hashing — direct bcrypt (passlib 1.7.4 is incompatible with bcrypt >= 4.x)
_BCRYPT_MAX_BYTES = 72  # bcrypt truncates inputs longer than 72 bytes


def _truncate(plain_password: str) -> bytes:
    """Encode the password and truncate to bcrypt's 72-byte limit."""
    return plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


# OAuth2 bearer scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt directly (cost factor 12)."""
    return _bcrypt_lib.hashpw(_truncate(plain_password), _bcrypt_lib.gensalt(12)).decode(
        "utf-8"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    if not hashed_password:
        return False
    try:
        return _bcrypt_lib.checkpw(_truncate(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    """Decode and validate a JWT access token. Raises HTTPException on failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: Any = payload.get("sub")
        email: Any = payload.get("email")
        role: Any = payload.get("role")
        if user_id is None and email is None:
            raise credentials_exception
        return TokenData(user_id=int(user_id) if user_id else None, email=email, role=role)
    except JWTError:
        raise credentials_exception


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """FastAPI dependency: resolve and return the authenticated User ORM object."""
    from sqlalchemy import select
    from app.infrastructure.database.models import User

    token_data = decode_access_token(token)

    stmt = select(User).where(
        User.id == token_data.user_id if token_data.user_id else User.email == token_data.email
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return user


async def get_current_active_user(
    current_user: Any = Depends(get_current_user),
) -> Any:
    """Dependency that asserts the user is active (alias for get_current_user)."""
    return current_user


def require_roles(*roles: str):
    """Factory for a dependency that requires one of the specified roles."""

    async def _require_roles(current_user: Any = Depends(get_current_user)) -> Any:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {list(roles)}",
            )
        return current_user

    return _require_roles
