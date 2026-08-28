"""User management endpoints (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, hash_password, require_roles
from app.infrastructure.database.models import AuditLog, User
from app.infrastructure.database.session import get_session
from app.schemas.auth import UserResponse, UserUpdate
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_or_404(user_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _write_audit(
    session: AsyncSession,
    actor: User,
    action: str,
    entity_id: int,
    old_val: dict | None = None,
    new_val: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=actor.id,
        action=action,
        entity_type="User",
        entity_id=str(entity_id),
        old_value_json=old_val,
        new_value_json=new_val,
    )
    session.add(entry)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> PaginatedResponse[UserResponse]:
    """List all users (admin only)."""
    total_result = await session.execute(select(func.count(User.id)))
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(User).order_by(User.id).offset(offset).limit(page_size)
    )
    users = result.scalars().all()
    items = [UserResponse.model_validate(u) for u in users]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> UserResponse:
    """Get a single user by ID (admin only)."""
    user = await _get_user_or_404(user_id, session)
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> UserResponse:
    """Update a user's details (admin only)."""
    user = await _get_user_or_404(user_id, session)

    old_val = {"role": user.role.value, "is_active": user.is_active}
    update_data = payload.model_dump(exclude_none=True)

    # Handle password separately — must be hashed
    if "password" in update_data:
        user.hashed_password = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    new_val = {"role": user.role.value, "is_active": user.is_active}
    await _write_audit(session, current_user, "user_update", user_id, old_val, new_val)

    await session.flush()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> None:
    """Soft-delete a user by deactivating them (admin only)."""
    user = await _get_user_or_404(user_id, session)

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    old_val = {"is_active": user.is_active}
    user.is_active = False
    await _write_audit(session, current_user, "user_deactivate", user_id, old_val, {"is_active": False})
    await session.flush()
