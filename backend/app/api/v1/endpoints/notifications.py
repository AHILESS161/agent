"""Notification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.infrastructure.database.models import Notification, User
from app.infrastructure.database.session import get_session
from app.schemas.notifications import (
    NotificationListResponse,
    NotificationMarkRead,
    NotificationResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# List / unread count
# ---------------------------------------------------------------------------


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """List notifications for the current user."""
    base_q = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        base_q = base_q.where(Notification.is_read == False)  # noqa: E712

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    unread_result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    unread_count = unread_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        base_q.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
    )
    notifications = result.scalars().all()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        unread_count=unread_count,
        total=total,
    )


@router.get("/unread-count")
async def get_unread_count(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Return the unread notification count for the current user."""
    result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return {"unread_count": result.scalar_one()}


# ---------------------------------------------------------------------------
# Mark read
# ---------------------------------------------------------------------------


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Mark a single notification as read."""
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    notif.is_read = True
    await session.flush()
    await session.refresh(notif)
    return NotificationResponse.model_validate(notif)


@router.post("/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read_bulk(
    payload: NotificationMarkRead,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Mark multiple notifications (or all) as read."""
    if payload.mark_all:
        await session.execute(
            update(Notification)
            .where(Notification.user_id == current_user.id)
            .values(is_read=True)
        )
    elif payload.notification_ids:
        await session.execute(
            update(Notification)
            .where(
                Notification.user_id == current_user.id,
                Notification.id.in_(payload.notification_ids),
            )
            .values(is_read=True)
        )
