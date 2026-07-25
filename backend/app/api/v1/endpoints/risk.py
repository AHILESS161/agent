"""Анализ рисков регистрации и решения специалиста по выводам."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import _get_llm_provider
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.infrastructure.database.models import (
    AuditLog,
    ReviewerDecision,
    RiskAssessment,
    RiskFinding,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services.risk_analysis import (
    run_absolute_grounds_analysis,
    serialize_assessment,
)

logger = get_logger(__name__)

router = APIRouter(tags=["risk-analysis"])

_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}


class FindingReviewRequest(BaseModel):
    decision: ReviewerDecision
    comment: str | None = Field(default=None, max_length=2000)


def _require_write_access(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для запуска анализа",
        )


async def _load_application(
    session: AsyncSession, application_id: int
) -> TrademarkApplicationDraft:
    application = (
        await session.execute(
            select(TrademarkApplicationDraft).where(
                TrademarkApplicationDraft.id == application_id
            )
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Дело {application_id} не найдено",
        )
    return application


def _loaded(query):
    """Подгрузить выводы и цитаты: в async-сессии ленивая загрузка невозможна."""
    return query.options(
        selectinload(RiskAssessment.findings).selectinload(RiskFinding.citations)
    )


@router.post(
    "/applications/{application_id}/risk-analysis",
    status_code=status.HTTP_201_CREATED,
    summary="Запустить анализ рисков по абсолютным основаниям",
)
async def run_analysis(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Оценить риски отказа с опорой на базу знаний.

    Каждый вывод обязан ссылаться на фрагмент нормативных материалов,
    и ссылка проверяется дословно. Вывод без подтверждённой цитаты
    отбрасывается, даже если выглядит убедительно.
    """
    _require_write_access(current_user)
    application = await _load_application(session, application_id)

    assessment = await run_absolute_grounds_analysis(
        session,
        application,
        llm_provider=_get_llm_provider(),
        user_id=current_user.id,
    )

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="risk_analysis.run",
            entity_type="RiskAssessment",
            entity_id=str(assessment.id),
            new_value_json={
                "overall_risk": (
                    assessment.overall_risk.value if assessment.overall_risk else None
                ),
                "inconclusive": assessment.is_inconclusive,
                "knowledge_base_version": assessment.knowledge_base_version,
            },
        )
    )
    await session.flush()

    # Перечитываем со связями для сериализации.
    loaded = (
        await session.execute(
            _loaded(select(RiskAssessment).where(RiskAssessment.id == assessment.id))
        )
    ).scalar_one()
    return serialize_assessment(loaded)


@router.get(
    "/applications/{application_id}/risk-analysis",
    summary="Последняя оценка рисков по делу",
)
async def get_latest_analysis(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_application(session, application_id)

    assessment = (
        await session.execute(
            _loaded(
                select(RiskAssessment)
                .where(RiskAssessment.application_id == application_id)
                .order_by(RiskAssessment.id.desc())
                .limit(1)
            )
        )
    ).scalar_one_or_none()

    if assessment is None:
        return {
            "application_id": application_id,
            "assessment": None,
            "message": "Анализ рисков по этому делу ещё не проводился",
        }
    return {"application_id": application_id, "assessment": serialize_assessment(assessment)}


@router.get(
    "/applications/{application_id}/risk-analysis/history",
    summary="История прогонов анализа",
)
async def get_analysis_history(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_application(session, application_id)

    assessments = (
        (
            await session.execute(
                select(RiskAssessment)
                .where(RiskAssessment.application_id == application_id)
                .order_by(RiskAssessment.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "application_id": application_id,
        "items": [
            {
                "id": item.id,
                "analysis_kind": item.analysis_kind.value,
                "overall_risk": item.overall_risk.value if item.overall_risk else None,
                "is_inconclusive": item.is_inconclusive,
                "knowledge_base_version": item.knowledge_base_version,
                "model_name": item.model_name,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in assessments
        ],
        "total": len(assessments),
    }


@router.post(
    "/risk-findings/{finding_id}/review",
    summary="Решение специалиста по выводу анализа",
)
async def review_finding(
    finding_id: int,
    payload: FindingReviewRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Согласиться с выводом, отклонить его или запросить доработку."""
    _require_write_access(current_user)

    finding = (
        await session.execute(
            select(RiskFinding)
            .where(RiskFinding.id == finding_id)
            .options(selectinload(RiskFinding.citations))
        )
    ).scalar_one_or_none()
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Вывод {finding_id} не найден",
        )

    finding.reviewer_id = current_user.id
    finding.reviewer_decision = payload.decision
    finding.reviewer_comment = payload.comment

    session.add(
        AuditLog(
            user_id=current_user.id,
            action=f"risk_finding.{payload.decision.value}",
            entity_type="RiskFinding",
            entity_id=str(finding.id),
            new_value_json={
                "category": finding.category,
                "decision": payload.decision.value,
            },
        )
    )
    await session.flush()

    logger.info(
        "Решение специалиста по выводу анализа",
        finding_id=finding.id,
        user_id=current_user.id,
        decision=payload.decision.value,
    )
    return {
        "id": finding.id,
        "category": finding.category,
        "reviewer_decision": finding.reviewer_decision.value,
        "reviewer_comment": finding.reviewer_comment,
    }
