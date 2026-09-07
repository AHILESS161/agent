"""Mandatory object authorization for every route in the case API routers."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.infrastructure.database.session import get_session
from app.infrastructure.database.models import (
    User, UserRole, TrademarkApplicationDraft, ApplicationDraft, RiskFinding, RiskAssessment,
)


def has_case_access(application: TrademarkApplicationDraft, user: User) -> bool:
    return (user.role == UserRole.admin or application.created_by_user_id == user.id
               or (user.role == UserRole.lawyer and application.assigned_lawyer_id == user.id)
               or (user.role == UserRole.manager and application.assigned_manager_id == user.id))


def require_case_access(application: TrademarkApplicationDraft, user: User) -> None:
    if not has_case_access(application, user):
        raise HTTPException(403, "Нет доступа к этой заявке")


async def authorize_case_route(request: Request, session: AsyncSession = Depends(get_session),
                               user: User = Depends(get_current_user)) -> None:
    params = request.path_params
    application_id = params.get("application_id")
    try:
        if application_id is not None:
            application_id = int(application_id)
        elif "draft_id" in params:
            application_id = await session.scalar(select(ApplicationDraft.application_id).where(
                ApplicationDraft.id == int(params["draft_id"])))
        elif "finding_id" in params:
            application_id = await session.scalar(select(RiskAssessment.application_id)
                .join(RiskFinding, RiskFinding.assessment_id == RiskAssessment.id)
                .where(RiskFinding.id == int(params["finding_id"])))
        else:
            return
    except (TypeError, ValueError):
        raise HTTPException(422, "Некорректный идентификатор")
    application = await session.get(TrademarkApplicationDraft, application_id) if application_id else None
    if application is None:
        raise HTTPException(404, "Заявка не найдена")
    require_case_access(application, user)
    request.state.application_id = application.id
