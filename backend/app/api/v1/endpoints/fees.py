"""Предварительный расчёт пошлин по заявке на товарный знак."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.infrastructure.database.models import TrademarkApplicationDraft, User, UserRole
from app.infrastructure.database.session import get_session
from app.services.fee_calculator import calculate_trademark_fees

router = APIRouter(prefix="/applications", tags=["fees"])


@router.get("/{application_id}/fees", summary="Рассчитать пошлины по выбранным классам")
async def application_fees(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    application = (
        await session.execute(
            select(TrademarkApplicationDraft).where(
                TrademarkApplicationDraft.id == application_id
            )
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    if current_user.role is not UserRole.admin and current_user.id not in {
        application.created_by_user_id,
        application.assigned_lawyer_id,
        application.assigned_manager_id,
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к расчёту")
    return await calculate_trademark_fees(session, application_id)
