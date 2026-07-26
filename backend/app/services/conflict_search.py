"""Поиск конфликтующих обозначений и оценка относительных оснований.

Проверка по пункту 6 статьи 1483 ГК РФ: тождество или сходство до
степени смешения с чужими знаками в отношении однородных товаров.

Сходство считается детерминированно (см. ``document_processing.similarity``),
а не языковой моделью: критерии формализованы в пункте 42 Правил № 482,
и расчёт по ним воспроизводим и проверяем.

Режим поиска обязательно фиксируется в оценке: сейчас доступен только
ограниченный демонстрационный набор данных, и выдавать его за полный
поиск по реестру недопустимо.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    AnalysisKind,
    ConflictSearchJob,
    ConflictSearchResult,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    SearchJobStatus,
    SearchMode,
    TrademarkApplicationDraft,
)
from app.document_processing.similarity import assess
from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.rag.store import knowledge_base_version
from app.services.class_analysis import load_class_context

logger = get_logger(__name__)

# Сколько записей запрашивать у провайдера на один вид поиска.
MAX_RESULTS = 50

# Порог, ниже которого совпадение не сохраняется как конфликт.
MIN_SIMILARITY = 0.3


def _search_mode() -> SearchMode:
    """Режим поиска по фактически настроенному провайдеру."""
    provider = (getattr(settings, "FIPS_PROVIDER", "mock") or "mock").lower()
    return SearchMode.demo if provider == "mock" else SearchMode.real


def _risk_level(similarity: float, confusion_likely: bool) -> RiskLevel:
    if similarity >= 0.9 and confusion_likely:
        return RiskLevel.critical
    if confusion_likely:
        return RiskLevel.high
    if similarity >= 0.5:
        return RiskLevel.medium
    return RiskLevel.low


async def run_conflict_search(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    registry_provider: Any,
    user_id: int | None = None,
) -> RiskAssessment:
    """Выполнить поиск конфликтов и сохранить оценку рисков."""
    mark_text = (application.mark_text or application.mark_name or "").strip()
    class_context = await load_class_context(session, application.id)
    classes = class_context.as_numbers()
    kb_version = await knowledge_base_version(session)
    mode = _search_mode()

    assessment = RiskAssessment(
        application_id=application.id,
        analysis_kind=AnalysisKind.relative_grounds,
        knowledge_base_version=kb_version,
        # Сходство считается правилами, а не моделью.
        llm_used=False,
        model_name=None,
        search_mode=mode,
        requires_specialist_review=True,
        classes_considered_json=classes,
        classes_confirmed=class_context.is_confirmed,
        created_by_user_id=user_id,
    )

    if not mark_text:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = "Недостаточно подтверждённых данных для вывода."
        assessment.missing_data_json = ["Заявляемое обозначение не указано"]
        assessment.limitations_json = [
            "Поиск не выполнялся: в деле отсутствует обозначение"
        ]
        session.add(assessment)
        await session.flush()
        return assessment

    job = ConflictSearchJob(
        application_id=application.id,
        status=SearchJobStatus.running,
        provider=getattr(settings, "FIPS_PROVIDER", "mock"),
        search_strategy_json={
            "mark_text": mark_text,
            "classes": classes,
            "search_types": ["exact", "fuzzy", "phonetic"],
        },
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.flush()

    # --- поиск ---
    records: dict[str, Any] = {}
    try:
        for search_type in ("exact", "fuzzy", "phonetic"):
            query = SearchQuery(
                mark_text=mark_text,
                mark_type=application.mark_type.value if application.mark_type else None,
                classes=classes or None,
                search_type=search_type,
                max_results=MAX_RESULTS,
            )
            for record in await registry_provider.search_marks(query):
                # Один знак может найтись несколькими видами поиска.
                records.setdefault(record.record_id, record)
    except Exception as exc:  # noqa: BLE001
        job.status = SearchJobStatus.failed
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = "Недостаточно подтверждённых данных для вывода."
        assessment.limitations_json = [f"Поиск по реестру не выполнен: {exc}"]
        session.add(assessment)
        await session.flush()
        logger.warning("Поиск конфликтов не выполнен", error=str(exc))
        return assessment

    # --- оценка сходства ---
    conflicts: list[tuple[Any, Any]] = []
    for record in records.values():
        similarity = assess(
            applicant_mark=mark_text,
            conflicting_mark=record.mark_text,
            applicant_classes=classes,
            conflicting_classes=record.classes,
            applicant_goods=application.goods_services_raw or "",
            conflicting_goods=" ".join(str(c) for c in record.classes),
        )
        if similarity.overall < MIN_SIMILARITY:
            continue

        session.add(
            ConflictSearchResult(
                search_job_id=job.id,
                application_id=application.id,
                provider=job.provider,
                source_record_id=record.record_id,
                matched_mark=record.mark_text,
                owner=record.owner,
                classes=record.classes,
                status=record.status,
                similarity_score=round(similarity.overall, 3),
            )
        )
        conflicts.append((record, similarity))

    conflicts.sort(key=lambda pair: pair[1].overall, reverse=True)

    job.status = SearchJobStatus.completed
    job.total_results = len(conflicts)
    job.completed_at = datetime.now(timezone.utc)

    # --- ограничения, которые обязаны попасть в отчёт ---
    limitations: list[str] = []
    if mode is SearchMode.demo:
        limitations.append(
            "Поиск выполнен по ограниченному демонстрационному набору данных, "
            "а не по полному реестру Роспатента. Полнота результатов "
            "не гарантируется."
        )
    limitations.append(
        "Проверены только зарегистрированные обозначения из доступного "
        "источника. Поданные заявки, общеизвестные знаки, НМПТ, фирменные "
        "наименования и объекты по пунктам 7–10 статьи 1483 не проверялись."
    )
    if not classes:
        limitations.append(
            "Классы МКТУ не определены — однородность товаров оценена "
            "приблизительно."
        )
    elif not class_context.is_confirmed:
        limitations.append(
            "Классы МКТУ не подтверждены специалистом. Оценка однородности "
            "может измениться после уточнения перечня."
        )

    missing: list[str] = []
    if not classes:
        missing.append("Перечень классов МКТУ")

    assessment.limitations_json = limitations
    assessment.missing_data_json = missing
    assessment.sources_used_json = [
        f"registry:{record.record_id}" for record, _ in conflicts
    ]
    assessment.verification_json = {
        "records_examined": len(records),
        "conflicts_found": len(conflicts),
        "method": "deterministic_similarity",
        "criteria": "п.42 Правил № 482; п.162 Пленума ВС РФ № 10",
    }

    if not conflicts:
        assessment.overall_risk = RiskLevel.low
        assessment.summary = (
            f"В доступном источнике совпадений с обозначением «{mark_text}» "
            "не обнаружено. Это не исключает наличия конфликтов в непроверенных "
            "источниках."
        )
        session.add(assessment)
        await session.flush()
        return assessment

    highest = conflicts[0][1]
    assessment.overall_risk = _risk_level(highest.overall, highest.confusion_likely)
    assessment.summary = (
        f"Обнаружено совпадений: {len(conflicts)}. Наибольшее сходство — "
        f"«{conflicts[0][0].mark_text}» ({highest.overall:.2f})."
    )
    session.add(assessment)
    await session.flush()

    # --- выводы по каждому конфликту ---
    for record, similarity in conflicts:
        explanation = (
            f"Обозначение «{mark_text}» сопоставлено с «{record.mark_text}» "
            f"(правообладатель: {record.owner or 'не указан'}). "
            f"Звуковое сходство {similarity.phonetic:.2f}, графическое "
            f"{similarity.visual:.2f}, смысловое {similarity.semantic:.2f}, "
            f"однородность товаров {similarity.goods:.2f}."
        )
        if similarity.reasons:
            explanation += " Основания: " + "; ".join(similarity.reasons) + "."

        session.add(
            RiskFinding(
                assessment_id=assessment.id,
                category="conflicting_mark",
                level=_risk_level(similarity.overall, similarity.confusion_likely),
                legal_basis="ГК РФ ст. 1483 п. 6",
                explanation=explanation,
                case_facts_json=[
                    f"Заявляемое обозначение: {mark_text}",
                    f"Классы МКТУ: {', '.join(map(str, classes)) or 'не определены'}",
                    f"Противопоставленный знак: {record.record_id}",
                ],
                missing_data_json=[],
                confidence=round(min(0.9, similarity.overall), 2),
                recommended_action=(
                    "Оценить вероятность смешения и рассмотреть получение "
                    "письма-согласия либо доработку обозначения"
                    if similarity.confusion_likely
                    else "Принять во внимание при итоговой оценке"
                ),
                # Источник — запись реестра, а не фрагмент базы знаний,
                # поэтому цитаты из нормативных материалов здесь нет.
                citations_verified=False,
                verification_json={
                    "source": "registry_record",
                    "record_id": record.record_id,
                    "similarity": similarity.as_dict(),
                },
            )
        )

    await session.flush()
    logger.info(
        "Поиск конфликтов выполнен",
        application_id=application.id,
        assessment_id=assessment.id,
        examined=len(records),
        conflicts=len(conflicts),
        mode=mode.value,
    )
    return assessment
