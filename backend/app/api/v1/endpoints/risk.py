"""Анализ рисков регистрации и решения специалиста по выводам."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import _get_llm_provider, _get_registry_provider
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.infrastructure.database.models import (
    AnalysisKind,
    AuditLog,
    ReviewerDecision,
    RiskAssessment,
    RiskFinding,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services.class_analysis import run_class_analysis
from app.services.conflict_search import run_conflict_search
from app.services.full_analysis import run_full_analysis
from app.services.nice_catalog import search as nice_catalog_search
from app.services.risk_analysis import (
    run_absolute_grounds_analysis,
    serialize_assessment,
)

logger = get_logger(__name__)

router = APIRouter(tags=["risk-analysis"])

_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}

# Один и тот же анализ нельзя запускать параллельно: в demo-режиме SQLite
# допускает только одного писателя, а два долгих запроса создают дубли
# оценок даже после перехода на PostgreSQL. Блокировка локальна процессу;
# production-защита для нескольких workers должна использовать Redis/job id.
_FULL_ANALYSIS_LOCKS: dict[int, asyncio.Lock] = {}


def _full_analysis_lock(application_id: int) -> asyncio.Lock:
    return _FULL_ANALYSIS_LOCKS.setdefault(application_id, asyncio.Lock())


class FindingReviewRequest(BaseModel):
    decision: ReviewerDecision
    comment: str | None = Field(default=None, max_length=2000)


def _require_write_access(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для запуска анализа",
        )


def _require_client_access(user: User, application: TrademarkApplicationDraft) -> None:
    if user.role is UserRole.client and application.created_by_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к анализу заявки",
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


@router.get(
    "/nice-classes/catalog",
    summary="Справочник классов МКТУ с поиском",
)
async def nice_class_catalog(
    q: str = "",
    limit: int = 20,
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Найти класс МКТУ по названию, составу или номеру.

    Нужен, чтобы выбирать класс по смыслу («одежда», «кофе»), а не
    вводить номер по памяти. Выборка справочная и детерминированная —
    языковая модель здесь не участвует.
    """
    found = nice_catalog_search(q, limit=max(1, min(limit, 45)))
    return {"query": q, "items": [item.as_dict() for item in found]}


@router.post(
    "/applications/{application_id}/full-analysis",
    status_code=status.HTTP_201_CREATED,
    summary="Полный правовой анализ: классы, абсолютные и относительные основания",
)
async def run_full(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Выполнить все проверки по делу в правильном порядке.

    Классы МКТУ определяются первыми: охраноспособность оценивается
    только в отношении конкретных товаров и услуг. Затем проверяются
    абсолютные основания и конфликты, и лишь по их совокупности
    формируется вердикт.
    """
    application = await _load_application(session, application_id)
    if current_user.role is UserRole.client:
        _require_client_access(current_user, application)
    else:
        _require_write_access(current_user)

    lock = _full_analysis_lock(application_id)
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Заключение по этому делу уже обновляется. "
                "Дождитесь завершения текущего анализа."
            ),
        )


    async with lock:
        result = await run_full_analysis(
            session,
            application,
            llm_provider=_get_llm_provider(),
            registry_provider=_get_registry_provider(),
            user_id=current_user.id,
        )

        session.add(
            AuditLog(
                user_id=current_user.id,
                application_id=application.id,
                action="full_analysis.run",
                entity_type="TrademarkApplicationDraft",
                entity_id=str(application.id),
                new_value_json={
                    "overall_risk": result["overall_risk"],
                    "verdict": result["verdict"],
                    "is_complete": result["is_complete"],
                },
            )
        )
        await session.flush()
        # Коммитим до освобождения блокировки: dependency делает финальный
        # commit уже после возврата из endpoint, и второй запрос иначе может
        # успеть начать запись в коротком промежутке между этими событиями.
        await session.commit()
        return result


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
    application = await _load_application(session, application_id)
    if current_user.role is UserRole.client:
        _require_client_access(current_user, application)
    else:
        _require_write_access(current_user)

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


@router.post(
    "/applications/{application_id}/nice-classes/suggest",
    status_code=status.HTTP_201_CREATED,
    summary="Подобрать классы МКТУ по описанию деятельности",
)
async def suggest_classes(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Определить классы МКТУ из описания деятельности заявителя.

    Классы влияют на оценку охраноспособности: обозначение описательно
    только применительно к конкретным товарам. Поэтому подбор классов
    выполняется до анализа оснований отказа, а его результат
    подтверждается специалистом.
    """
    _require_write_access(current_user)
    application = await _load_application(session, application_id)

    result = await run_class_analysis(
        session, application, llm_provider=_get_llm_provider()
    )

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="nice_classes.suggest",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(application.id),
            new_value_json={
                "status": result.get("status"),
                "suggested": len(result.get("suggestions", [])),
            },
        )
    )
    await session.flush()
    return result


@router.post(
    "/applications/{application_id}/conflict-search",
    status_code=status.HTTP_201_CREATED,
    summary="Поиск конфликтующих обозначений (относительные основания)",
)
async def run_conflicts(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Проверка по пункту 6 статьи 1483 ГК РФ.

    Сходство обозначений оценивается детерминированно по критериям
    пункта 42 Правил № 482, вероятность смешения — по пункту 162
    постановления Пленума ВС РФ № 10. Режим поиска (реальный или
    демонстрационный) фиксируется в оценке.

    Языковая модель привлекается только к смысловому сходству
    обозначений на разных языках — критерию, который правилами
    не считается.
    """
    _require_write_access(current_user)
    application = await _load_application(session, application_id)

    assessment = await run_conflict_search(
        session,
        application,
        registry_provider=_get_registry_provider(),
        user_id=current_user.id,
        llm_provider=_get_llm_provider(),
    )

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="conflict_search.run",
            entity_type="RiskAssessment",
            entity_id=str(assessment.id),
            new_value_json={
                "overall_risk": (
                    assessment.overall_risk.value if assessment.overall_risk else None
                ),
                "search_mode": assessment.search_mode.value,
            },
        )
    )
    await session.flush()

    loaded = (
        await session.execute(
            _loaded(select(RiskAssessment).where(RiskAssessment.id == assessment.id))
        )
    ).scalar_one()
    return serialize_assessment(loaded)


@router.get(
    "/applications/{application_id}/risk-report",
    summary="Сводный отчёт о рисках по обоим основаниям",
)
async def risk_report(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Собрать последние оценки по абсолютным и относительным основаниям.

    Итоговый уровень — наибольший из двух: наличие любого серьёзного
    основания определяет риск в целом.
    """
    application = await _load_application(session, application_id)
    _require_client_access(current_user, application)

    sections: dict[str, Any] = {}
    for kind in (AnalysisKind.absolute_grounds, AnalysisKind.relative_grounds):
        latest = (
            await session.execute(
                _loaded(
                    select(RiskAssessment)
                    .where(
                        RiskAssessment.application_id == application_id,
                        RiskAssessment.analysis_kind == kind,
                    )
                    .order_by(RiskAssessment.id.desc())
                    .limit(1)
                )
            )
        ).scalar_one_or_none()
        sections[kind.value] = serialize_assessment(latest) if latest else None

    order = ["low", "medium", "high", "critical"]
    levels = [
        section["overall_risk"]
        for section in sections.values()
        if section and section.get("overall_risk")
    ]
    overall = max(levels, key=order.index) if levels else None

    limitations: list[str] = []
    for section in sections.values():
        if section:
            limitations.extend(section.get("limitations", []))

    missing_sections = [name for name, section in sections.items() if section is None]
    section_labels = {
        "absolute_grounds": "проверка самого обозначения по основаниям отказа",
        "relative_grounds": "поиск сходных зарегистрированных знаков и заявок",
    }
    inconclusive_sections = [
        section.get("inconclusive_reason") or f"Не завершена {section_labels.get(name, name)}"
        for name, section in sections.items()
        if section and section.get("is_inconclusive")
    ]
    class_contexts = [
        section
        for section in sections.values()
        if section and section.get("classes_considered")
    ]
    classes_confirmed = bool(class_contexts) and all(
        section.get("classes_confirmed") for section in class_contexts
    )
    incomplete_checks = [
        f"Не выполнена {section_labels.get(name, name)}"
        for name in missing_sections
    ] + inconclusive_sections
    if not classes_confirmed:
        incomplete_checks.append(
            "Не подтверждены классы товаров и услуг, поэтому область поиска пока не зафиксирована"
        )
    is_complete = not missing_sections and not inconclusive_sections and classes_confirmed

    # Неполная проверка не должна сохраняться на клиентском экране как
    # зелёное «можно продолжать», даже если завершённая часть имеет low.
    if not is_complete and overall in {None, "low"}:
        overall = None

    return {
        "application_id": application_id,
        "mark": application.mark_text or application.mark_name,
        "overall_risk": overall,
        "sections": sections,
        "missing_sections": missing_sections,
        "incomplete_checks": incomplete_checks,
        "classes_confirmed": classes_confirmed,
        "limitations": limitations,
        "is_complete": is_complete,
        "requires_specialist_review": True,
        "disclaimer": (
            "Результаты сформированы с применением AI и носят предварительный "
            "информационный характер. Они требуют проверки специалистом. "
            "Отчёт не является юридическим заключением."
        ),
    }


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
