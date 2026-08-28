"""Audit log endpoints (admin / lawyer only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.infrastructure.database.models import (
    AuditLog,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse:
    """Thin response shape for audit log entries — not a Pydantic model intentionally,
    returned as plain dict to avoid heavy schema overhead."""


def _serialize_log(log: AuditLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "application_id": log.application_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "old_value_json": log.old_value_json,
        "new_value_json": log.new_value_json,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat(),
    }


@router.get("")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    entity_type: Optional[str] = Query(default=None),
    application_id: Optional[int] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> dict[str, Any]:
    """List audit log entries with optional filters.

    Returns paginated results with the following filters:
    - entity_type: filter by model name (e.g. 'TrademarkApplicationDraft')
    - application_id: filter by related application
    - user_id: filter by actor
    - date_from / date_to: ISO datetime range filter
    """
    base_q = select(AuditLog)

    # Администратор видит общий журнал. Юристу доступны только события по
    # делам, которые он создал или ведёт. Записи без application_id намеренно
    # исключены: в них могут быть сведения о чужих клиентах и пользователях.
    if current_user.role is UserRole.lawyer:
        accessible_applications = select(TrademarkApplicationDraft.id).where(
            or_(
                TrademarkApplicationDraft.created_by_user_id == current_user.id,
                TrademarkApplicationDraft.assigned_lawyer_id == current_user.id,
                TrademarkApplicationDraft.assigned_manager_id == current_user.id,
            )
        )
        base_q = base_q.where(AuditLog.application_id.in_(accessible_applications))

    if entity_type:
        base_q = base_q.where(AuditLog.entity_type == entity_type)
    if application_id is not None:
        base_q = base_q.where(AuditLog.application_id == application_id)
    if user_id is not None:
        base_q = base_q.where(AuditLog.user_id == user_id)
    if date_from is not None:
        base_q = base_q.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        base_q = base_q.where(AuditLog.created_at <= date_to)

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        base_q.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    )
    logs = result.scalars().all()

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": [_serialize_log(lg) for lg in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
