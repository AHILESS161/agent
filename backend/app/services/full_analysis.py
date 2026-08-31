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

from collections.abc import Awaitable, Callable
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
    SearchMode,
    TrademarkApplicationDraft,
)
from app.services.class_analysis import load_class_context, run_class_analysis
from app.services.conflict_search import run_conflict_search
from app.services.risk_analysis import AnalysisContext, run_absolute_grounds_analysis

logger = get_logger(__name__)

ProgressCallback = Callable[[str, int, str], Awaitable[None]]

# Порядок уровней риска — от меньшего к большему.
_RISK_ORDER = [RiskLevel.low, RiskLevel.medium, RiskLevel.high, RiskLevel.critical]

# Relative grounds are useful only after the designation has passed the first
# legal filter.  A high/critical absolute-ground risk is an independent reason
# for refusal, so querying the registry at that point adds latency and noise to
# the client report without changing the recommended next action.
_ABSOLUTE_GROUNDS_STOP_LEVELS = {RiskLevel.high, RiskLevel.critical}

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


def _is_pipeline_skip(assessment: RiskAssessment | None) -> bool:
    return bool(
        assessment
        and isinstance(assessment.verification_json, dict)
        and assessment.verification_json.get("skipped") is True
        and assessment.verification_json.get("blocked_by") == "absolute_grounds"
    )


async def _skip_relative_grounds(
    session: AsyncSession,
    *,
    application_id: int,
    classes: list[int],
    classes_confirmed: bool,
    user_id: int | None,
    absolute: RiskAssessment,
) -> RiskAssessment:
    """Persist an explicit pipeline decision without pretending a search ran."""
    latest = await _latest(session, application_id, AnalysisKind.relative_grounds)
    expected_classes = sorted(set(classes))
    if (
        _is_pipeline_skip(latest)
        and sorted(set(latest.classes_considered_json or [])) == expected_classes
        and latest.classes_confirmed == classes_confirmed
        and (latest.verification_json or {}).get("absolute_assessment_id") == absolute.id
    ):
        return latest

    absolute_unavailable = absolute.is_inconclusive
    if absolute_unavailable:
        summary = (
            "Поиск похожих товарных знаков пока не запускался: сначала нужно "
            "надёжно завершить проверку самого обозначения по основаниям отказа."
        )
        skip_reason = "Не завершена проверка абсолютных оснований."
    else:
        summary = (
            "Поиск похожих товарных знаков не проводился: проверка самого "
            "обозначения уже выявила самостоятельное существенное основание для "
            "отказа. Сначала рекомендуется изменить знак, затем повторить анализ."
        )
        skip_reason = (
            "Высокий или критический риск по абсолютным основаниям делает поиск "
            "сходных знаков преждевременным."
        )

    assessment = RiskAssessment(
        application_id=application_id,
        analysis_kind=AnalysisKind.relative_grounds,
        overall_risk=None,
        summary=summary,
        limitations_json=[],
        missing_data_json=(
            ["Надёжный результат проверки абсолютных оснований"]
            if absolute_unavailable
            else []
        ),
        is_inconclusive=absolute_unavailable,
        inconclusive_reason=summary if absolute_unavailable else None,
        knowledge_base_version=absolute.knowledge_base_version,
        model_name=None,
        llm_used=False,
        search_mode=SearchMode.not_performed,
        sources_used_json=[],
        verification_json={
            "skipped": True,
            "blocked_by": "absolute_grounds",
            "skip_reason": skip_reason,
            "absolute_assessment_id": absolute.id,
            "blocking_risk": (
                absolute.overall_risk.value if absolute.overall_risk else None
            ),
            "search_complete": False,
        },
        requires_specialist_review=True,
        created_by_user_id=user_id,
        classes_considered_json=expected_classes,
        classes_confirmed=classes_confirmed,
    )
    session.add(assessment)
    await session.flush()
    return assessment


async def latest_completed_for_classes(
    session: AsyncSession,
    application_id: int,
    kind: AnalysisKind,
    *,
    classes: list[int],
    classes_confirmed: bool,
    input_fingerprint: str | None = None,
) -> RiskAssessment | None:
    """Вернуть последний пригодный результат для тех же подтверждённых классов.

    Внешний реестр или LLM могут временно не ответить при повторном запуске.
    Такая попытка не должна уничтожать уже завершённую проверку, но старый
    результат допустимо переиспользовать только для той же области охраны.
    """
    candidates = list(
        (
            await session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.application_id == application_id,
                    RiskAssessment.analysis_kind == kind,
                    RiskAssessment.is_inconclusive.is_(False),
                )
                .order_by(RiskAssessment.id.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    expected = sorted(set(classes))
    for candidate in candidates:
        considered = sorted(set(candidate.classes_considered_json or []))
        if (
            considered == expected
            and candidate.classes_confirmed == classes_confirmed
            and (
                input_fingerprint is None
                or (candidate.verification_json or {}).get("input_fingerprint")
                == input_fingerprint
            )
        ):
            return candidate
    return None


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
    def _risk_explanations(assessment_id: int) -> Any:
        """Только неблагоприятные выводы, а не перечень пройденных проверок."""
        return select(RiskFinding.explanation).where(
            RiskFinding.assessment_id == assessment_id,
            RiskFinding.level.in_((RiskLevel.medium, RiskLevel.high, RiskLevel.critical)),
        )

    absolute_risks = list(
        (await session.execute(_risk_explanations(absolute.id))).scalars().all()
    )
    relative_risks = list(
        (await session.execute(_risk_explanations(relative.id))).scalars().all()
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
    progress_callback: ProgressCallback | None = None,
    retry_incomplete_only: bool = False,
) -> dict[str, Any]:
    """Выполнить все проверки по делу и собрать общий вердикт."""
    steps: list[dict[str, Any]] = []

    async def progress(step: str, percent: int, detail: str) -> None:
        if progress_callback is not None:
            await progress_callback(step, percent, detail)

    # --- 1. Классы МКТУ ---------------------------------------------------
    # От перечня классов зависит вывод об охраноспособности, поэтому
    # он определяется до правовых проверок. Уже подтверждённые
    # специалистом классы не трогаются.
    await progress("classes", 10, "Проверяем выбранные классы товаров и услуг")
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
    absolute_input_fingerprint = AnalysisContext.from_application(
        application, class_context
    ).fingerprint()
    refresh_warnings: list[dict[str, str]] = []

    # --- 2. Абсолютные основания -----------------------------------------
    await progress("absolute_grounds", 35, "Проверяем само обозначение")
    absolute = (
        await _latest(session, application.id, AnalysisKind.absolute_grounds)
        if retry_incomplete_only
        else None
    )
    if absolute is None or absolute.is_inconclusive:
        previous_absolute = await latest_completed_for_classes(
            session,
            application.id,
            AnalysisKind.absolute_grounds,
            classes=classes,
            classes_confirmed=class_context.is_confirmed,
            input_fingerprint=absolute_input_fingerprint,
        )
        absolute_attempt = await run_absolute_grounds_analysis(
            session, application, llm_provider=llm_provider, user_id=user_id
        )
        if absolute_attempt.is_inconclusive and previous_absolute is not None:
            refresh_warnings.append(
                {
                    "step": "absolute_grounds",
                    "detail": absolute_attempt.inconclusive_reason
                    or "Повторную правовую проверку временно не удалось завершить.",
                }
            )
            absolute = previous_absolute
            absolute_status = "reused_after_refresh_failure"
        else:
            absolute = absolute_attempt
            absolute_status = "inconclusive" if absolute.is_inconclusive else "ok"
    else:
        absolute_status = "reused"
    steps.append(
        {
            "step": "absolute_grounds",
            "status": absolute_status,
            "detail": absolute.inconclusive_reason or absolute.summary,
        }
    )

    # --- 3. Относительные основания --------------------------------------
    # Это последовательный юридический pipeline, а не два независимых запроса.
    # Пока абсолютные основания не проверены надёжно, реестр не запрашиваем.
    # При high/critical поиск также не нужен: уже найдено самостоятельное
    # препятствие, которое сначала необходимо устранить.
    absolute_stops_pipeline = (
        absolute.is_inconclusive
        or absolute.overall_risk in _ABSOLUTE_GROUNDS_STOP_LEVELS
    )
    if absolute_stops_pipeline:
        await progress(
            "relative_grounds",
            60,
            (
                "Останавливаем проверку до завершения анализа самого обозначения"
                if absolute.is_inconclusive
                else "Поиск похожих знаков не требуется: сначала нужно изменить обозначение"
            ),
        )
        relative = await _skip_relative_grounds(
            session,
            application_id=application.id,
            classes=classes,
            classes_confirmed=class_context.is_confirmed,
            user_id=user_id,
            absolute=absolute,
        )
        relative_status = "blocked" if absolute.is_inconclusive else "not_required"
    else:
        await progress("relative_grounds", 60, "Ищем сходные знаки прежде всего в выбранных классах")
        relative = (
            await _latest(session, application.id, AnalysisKind.relative_grounds)
            if retry_incomplete_only
            else None
        )
        # A previous pipeline skip is not a registry result.  Once the absolute
        # risk has been removed, the registry phase must run normally.
        if _is_pipeline_skip(relative):
            relative = None
        if relative is None or relative.is_inconclusive:
            previous_relative = await latest_completed_for_classes(
                session,
                application.id,
                AnalysisKind.relative_grounds,
                classes=classes,
                classes_confirmed=class_context.is_confirmed,
            )
            if _is_pipeline_skip(previous_relative):
                previous_relative = None
            relative_attempt = await run_conflict_search(
                session,
                application,
                registry_provider=registry_provider,
                user_id=user_id,
                llm_provider=llm_provider,
            )
            if relative_attempt.is_inconclusive and previous_relative is not None:
                refresh_warnings.append(
                    {
                        "step": "relative_grounds",
                        "detail": relative_attempt.inconclusive_reason
                        or "Повторный поиск по реестру временно не удалось завершить.",
                    }
                )
                relative = previous_relative
                relative_status = "reused_after_refresh_failure"
            else:
                relative = relative_attempt
                relative_status = "inconclusive" if relative.is_inconclusive else "ok"
        else:
            relative_status = "reused"
    steps.append(
        {
            "step": "relative_grounds",
            "status": relative_status,
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
    if relative.is_inconclusive and not _is_pipeline_skip(relative):
        incomplete.append("относительные основания (ст. 1483 п. 6)")
    if not classes:
        incomplete.append("классы МКТУ не определены")

    if classes and not class_context.is_confirmed:
        incomplete.append("классы МКТУ не подтверждены специалистом")

    # Неполный контур с единственным уровнем low не должен превращаться в
    # успокаивающее «рисков нет». Сохраняем конкретные локальные выводы внутри
    # секций, но общий уровень оставляем неопределённым.
    if incomplete and overall in {None, RiskLevel.low}:
        overall = None
        verdict_code, verdict_text = (
            "inconclusive",
            "Проверка не завершена: отсутствие выявленных рисков не означает их отсутствие.",
        )
    elif overall is None:
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
    await progress("recommendation", 90, "Готовим понятный вывод и рекомендации")
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

    result = {
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
        "refresh_warnings": refresh_warnings,
        "requires_specialist_review": True,
        "disclaimer": (
            "Результаты сформированы с применением AI и носят предварительный "
            "информационный характер. Они требуют проверки специалистом."
        ),
    }
    await progress("completed", 100, "Проверка завершена")
    return result
