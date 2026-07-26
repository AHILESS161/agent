"""Полный правовой анализ дела в один проход.

Проверки нельзя запускать в произвольном порядке. Охраноспособность
оценивается не сама по себе, а в отношении конкретных товаров и услуг:
одно и то же обозначение бывает описательным для одних классов и
фантазийным для других. Поэтому порядок жёсткий:

    1. классы МКТУ (если ещё не определены)
    2. абсолютные основания — статья 1483, пункты 1–5
    3. относительные основания — пункт 6, поиск конфликтов
    4. сводный вердикт по совокупности

Вердикт складывается из обоих блоков: наличие любого серьёзного
основания определяет итог. Ни один шаг не подтверждается системой —
итог остаётся предварительным до проверки специалистом.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    AnalysisKind,
    NiceClassSuggestion,
    RecommendationMemo,
    RecommendedAction,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    TrademarkApplicationDraft,
)
from app.services.class_analysis import load_class_context, run_class_analysis
from app.services.conflict_search import run_conflict_search
from app.services.risk_analysis import run_absolute_grounds_analysis

logger = get_logger(__name__)

# Порядок уровней риска — от меньшего к большему.
_RISK_ORDER = [RiskLevel.low, RiskLevel.medium, RiskLevel.high, RiskLevel.critical]

_VERDICT_BY_RISK: dict[RiskLevel, tuple[str, str]] = {
    RiskLevel.low: (
        "proceed",
        "Существенных препятствий не выявлено. Регистрация возможна.",
    ),
    RiskLevel.medium: (
        "proceed_with_caution",
        "Выявлены замечания. Регистрация возможна, но требует доработки "
        "заявки или уточнения перечня товаров.",
    ),
    RiskLevel.high: (
        "revise",
        "Выявлены серьёзные основания для отказа. Обозначение или перечень "
        "товаров рекомендуется пересмотреть.",
    ),
    RiskLevel.critical: (
        "do_not_proceed",
        "Выявлены основания, с высокой вероятностью влекущие отказ. "
        "Подача в текущем виде не рекомендуется.",
    ),
}


def _max_risk(levels: list[RiskLevel]) -> RiskLevel | None:
    if not levels:
        return None
    return max(levels, key=_RISK_ORDER.index)


async def _latest(
    session: AsyncSession, application_id: int, kind: AnalysisKind
) -> RiskAssessment | None:
    return (
        await session.execute(
            select(RiskAssessment)
            .where(
                RiskAssessment.application_id == application_id,
                RiskAssessment.analysis_kind == kind,
            )
            .order_by(RiskAssessment.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# Вердикт анализа -> действие, предусмотренное меморандумом.
_ACTION_BY_VERDICT: dict[str, RecommendedAction] = {
    "proceed": RecommendedAction.proceed,
    "proceed_with_caution": RecommendedAction.proceed,
    "revise": RecommendedAction.modify,
    "do_not_proceed": RecommendedAction.withdraw,
    "inconclusive": RecommendedAction.further_review,
}


async def _save_memo(
    session: AsyncSession,
    *,
    application_id: int,
    verdict_code: str,
    verdict_text: str,
    overall: RiskLevel | None,
    classes: list[int],
    absolute: RiskAssessment,
    relative: RiskAssessment,
    incomplete: list[str],
    user_id: int | None,
) -> None:
    """Сохранить итог анализа как меморандум по делу.

    Меморандум не утверждается системой: поле ``approved_by`` остаётся
    пустым, пока специалист не подтвердит вывод. Пересчёт анализа
    обновляет существующий меморандум, а не плодит копии.
    """
    memo = (
        await session.execute(
            select(RecommendationMemo)
            .where(RecommendationMemo.application_id == application_id)
            .order_by(RecommendationMemo.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if memo is None:
        memo = RecommendationMemo(application_id=application_id)
        session.add(memo)

    # Связь findings ленивая: в async-сессии её нельзя трогать
    # напрямую, поэтому выводы читаются отдельным запросом.
    def _explanations(assessment_id: int) -> Any:
        return select(RiskFinding.explanation).where(
            RiskFinding.assessment_id == assessment_id
        )

    absolute_risks = list(
        (await session.execute(_explanations(absolute.id))).scalars().all()
    )
    relative_risks = list(
        (await session.execute(_explanations(relative.id))).scalars().all()
    )

    memo.recommended_action = _ACTION_BY_VERDICT.get(
        verdict_code, RecommendedAction.further_review
    )
    memo.summary = verdict_text
    memo.risk_assessment = " ".join(
        part
        for part in (
            f"Итоговый уровень риска: {overall.value}." if overall else None,
            absolute.summary,
            relative.summary,
        )
        if part
    ) or None
    memo.recommended_classes_json = classes
    memo.key_risks_json = (absolute_risks + relative_risks)[:10]
    memo.key_conflicts_json = relative_risks[:10]
    memo.evidence_json = {
        "absolute_assessment_id": absolute.id,
        "relative_assessment_id": relative.id,
        "incomplete_checks": incomplete,
    }
    # Уверенность ограничена: вывод предварительный по определению.
    memo.confidence = None if incomplete else 0.8
    # Решение специалиста сбрасывается: выводы пересчитаны.
    memo.approved_by = None
    memo.approved_at = None
    await session.flush()


async def run_full_analysis(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    llm_provider: Any,
    registry_provider: Any,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Выполнить все проверки по делу и собрать общий вердикт."""
    steps: list[dict[str, Any]] = []

    # --- 1. Классы МКТУ ---------------------------------------------------
    # От перечня классов зависит вывод об охраноспособности, поэтому
    # он определяется до правовых проверок. Уже подтверждённые
    # специалистом классы не трогаются.
    class_context = await load_class_context(session, application.id)
    if class_context.as_numbers():
        steps.append(
            {
                "step": "classes",
                "status": "skipped",
                "detail": "Классы уже определены — повторный подбор не требуется.",
            }
        )
    else:
        result = await run_class_analysis(session, application, llm_provider)
        steps.append(
            {
                "step": "classes",
                "status": result.get("status", "unknown"),
                "detail": result.get("reason")
                or f"Предложено классов: {len(result.get('suggestions') or [])}",
            }
        )
        class_context = await load_class_context(session, application.id)

    classes = class_context.as_numbers()

    # --- 2. Абсолютные основания -----------------------------------------
    absolute = await run_absolute_grounds_analysis(
        session, application, llm_provider=llm_provider, user_id=user_id
    )
    steps.append(
        {
            "step": "absolute_grounds",
            "status": "inconclusive" if absolute.is_inconclusive else "ok",
            "detail": absolute.inconclusive_reason or absolute.summary,
        }
    )

    # --- 3. Относительные основания --------------------------------------
    relative = await run_conflict_search(
        session,
        application,
        registry_provider=registry_provider,
        user_id=user_id,
        llm_provider=llm_provider,
    )
    steps.append(
        {
            "step": "relative_grounds",
            "status": "inconclusive" if relative.is_inconclusive else "ok",
            "detail": relative.inconclusive_reason or relative.summary,
        }
    )

    # --- 4. Сводный вердикт ----------------------------------------------
    levels = [a.overall_risk for a in (absolute, relative) if a.overall_risk]
    overall = _max_risk(levels)

    # Незавершённая проверка не должна выглядеть как «препятствий нет».
    incomplete: list[str] = []
    if absolute.is_inconclusive:
        incomplete.append("абсолютные основания (ст. 1483 п. 1–5)")
    if relative.is_inconclusive:
        incomplete.append("относительные основания (ст. 1483 п. 6)")
    if not classes:
        incomplete.append("классы МКТУ не определены")

    if overall is None:
        verdict_code, verdict_text = (
            "inconclusive",
            "Недостаточно подтверждённых данных для вывода.",
        )
    else:
        verdict_code, verdict_text = _VERDICT_BY_RISK[overall]

    limitations: list[str] = []
    for assessment in (absolute, relative):
        limitations.extend(assessment.limitations_json or [])

    # --- 5. Меморандум --------------------------------------------------
    # Итог анализа должен оставаться в деле, а не только на экране:
    # раздел «Рекомендации» читает именно его.
    await _save_memo(
        session,
        application_id=application.id,
        verdict_code=verdict_code,
        verdict_text=verdict_text,
        overall=overall,
        classes=classes,
        absolute=absolute,
        relative=relative,
        incomplete=incomplete,
        user_id=user_id,
    )

    logger.info(
        "Полный анализ выполнен",
        application_id=application.id,
        overall_risk=overall.value if overall else None,
        classes=len(classes),
        incomplete=len(incomplete),
    )

    return {
        "application_id": application.id,
        "overall_risk": overall.value if overall else None,
        "verdict": verdict_code,
        "verdict_text": verdict_text,
        "classes_considered": classes,
        "classes_confirmed": class_context.is_confirmed,
        "steps": steps,
        "incomplete_checks": incomplete,
        "is_complete": not incomplete,
        "limitations": limitations,
        "requires_specialist_review": True,
        "disclaimer": (
            "Результаты сформированы с применением AI и носят предварительный "
            "информационный характер. Они требуют проверки специалистом."
        ),
    }
