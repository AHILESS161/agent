"""Audit-backed confirmation of client-entered and extracted application data."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import AuditLog, TrademarkApplicationDraft


async def data_confirmation_state(
    session: AsyncSession, application: TrademarkApplicationDraft
) -> dict[str, Any]:
    confirmation_id = (
        await session.execute(
            select(func.max(AuditLog.id)).where(
                AuditLog.application_id == application.id,
                AuditLog.action == "application.data.confirmed",
            )
        )
    ).scalar_one_or_none()
    latest_application_change = (
        await session.execute(
            select(func.max(AuditLog.id)).where(
                AuditLog.application_id == application.id,
                AuditLog.action == "application_update",
            )
        )
    ).scalar_one_or_none()
    latest_class_change = (
        await session.execute(
            select(func.max(AuditLog.id)).where(
                AuditLog.application_id == application.id,
                AuditLog.action.in_(
                    {
                        "class_approve",
                        "class_reject",
                        "class_added_manually",
                        "class_deleted",
                    }
                ),
            )
        )
    ).scalar_one_or_none()
    latest_client_change = (
        await session.execute(
            select(func.max(AuditLog.id)).where(
                AuditLog.entity_type == "Client",
                AuditLog.entity_id == str(application.client_id),
                AuditLog.action == "client_update",
            )
        )
    ).scalar_one_or_none()
    latest_representative_change = None
    if application.representative_id:
        latest_representative_change = (
            await session.execute(
                select(func.max(AuditLog.id)).where(
                    AuditLog.entity_type == "ClientRepresentative",
                    AuditLog.entity_id == str(application.representative_id),
                    AuditLog.action.in_({"representative_add", "representative_update"}),
                )
            )
        ).scalar_one_or_none()
    latest_change = max(
        latest_application_change or 0,
        latest_class_change or 0,
        latest_client_change or 0,
        latest_representative_change or 0,
    )
    confirmed = bool(confirmation_id and confirmation_id > latest_change)
    return {
        "confirmed": confirmed,
        "confirmation_id": confirmation_id if confirmed else None,
    }
