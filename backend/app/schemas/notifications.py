"""Notification Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.infrastructure.database.models import NotificationType


class NotificationResponse(BaseModel):
    """Public notification representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    application_id: Optional[int] = None
    type: NotificationType
    title: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationMarkRead(BaseModel):
    """Payload for marking one or more notifications as read."""

    notification_ids: List[int]
    mark_all: bool = False


class NotificationListResponse(BaseModel):
    """Response for listing notifications."""

    items: List[NotificationResponse]
    unread_count: int
    total: int
