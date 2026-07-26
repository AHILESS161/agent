"""Поиск конфликтующих обозначений и оценка относительных оснований.

Проверка по пункту 6 статьи 1483 ГК РФ: тождество или сходство до
степени смешения с чужими знаками в отношении однородных товаров.

Сходство считается детерминированно (см. ``document_processing.similarity``),
а не языковой моделью: критерии формализованы в пункте 42 Правил № 482,
и расчёт по ним воспроизводим и проверяем.

Исключение — смысловое сходство обозначений на разных языках. Пункт 42
прямо относит к нему «совпадение значения обозначений в разных языках»,
а правилами это не считается: «ЯБЛОКО» и «APPLE» не совпадают ни звуком,
ни начертанием. Здесь вызывается языковая модель — но только для пар,
где её ответ способен изменить вывод, и только на повышение оценки.

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
from app.agents.legal.query_variants import QueryVariantGenerator
from app.agents.legal.semantic_similarity import (
    SemanticSimilarityAnalyzer,
    SemanticVerdict,
    describe,
    needs_semantic_check,
)
from app.document_processing.similarity import assess, with_semantic
from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.rag.store import knowledge_base_version
from app.services.class_analysis import load_class_context

logger = get_logger(__name__)

# Сколько записей запрашивать у провайдера на один вид поиска.
MAX_RESULTS = 50

# Порог, ниже которого совпадение не сохраняется как конфликт.
MIN_SIMILARITY = 0.3

# Потолок на число обращений к модели за один поиск. Смысловая проверка
# идёт по парам, и без ограничения большая выдача обошлась бы дорого;
# пары берутся в порядке убывания однородности товаров — там смысловое
# совпадение опаснее всего.
MAX_SEMANTIC_CHECKS = 12


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


async def _apply_semantic_layer(
    scored: list[tuple[Any, Any]],
    mark_text: str,
    llm_provider: Any,
    goods_known: bool,
) -> tuple[list[tuple[Any, Any]], dict[str, SemanticVerdict]]:
    """Уточнить смысловое сходство языковой моделью там, где это решает.

    Возвращает пересчитанные оценки и заключения модели по тем парам,
    где связь действительно найдена. Без провайдера модели ничего
    не меняется: детерминированный расчёт остаётся как есть.
    """
    verdicts: dict[str, SemanticVerdict] = {}
    if llm_provider is None:
        return scored, verdicts

    candidates = [
        index
        for index, (record, similarity) in enumerate(scored)
        if needs_semantic_check(
            similarity, mark_text, record.mark_text or "", goods_known=goods_known
        )
    ]
    # Однородность товаров важнее: там смысловое совпадение опаснее.
    candidates.sort(key=lambda index: scored[index][1].goods, reverse=True)
    if len(candidates) > MAX_SEMANTIC_CHECKS:
        logger.info(
            "Смысловая проверка ограничена лимитом",
            candidates=len(candidates),
            limit=MAX_SEMANTIC_CHECKS,
        )
        candidates = candidates[:MAX_SEMANTIC_CHECKS]

    analyzer = SemanticSimilarityAnalyzer(llm_provider)
    updated = list(scored)
    for index in candidates:
        record, similarity = updated[index]
        verdict = await analyzer.analyze(mark_text, record.mark_text or "")
        if not verdict.is_meaningful:
            continue
        updated[index] = (record, with_semantic(similarity, verdict.score))
        verdicts[record.record_id] = verdict

    return updated, verdicts


async def run_conflict_search(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    registry_provider: Any,
    user_id: int | None = None,
    llm_provider: Any = None,
) -> RiskAssessment:
    """Выполнить поиск конфликтов и сохранить оценку рисков.

    ``llm_provider`` нужен только для смысловой проверки обозначений
    на разных языках. Без него поиск работает полностью на правилах.
    """
    mark_text = (application.mark_text or application.mark_name or "").strip()
    class_context = await load_class_context(session, application.id)
    classes = class_context.as_numbers()
    kb_version = await knowledge_base_version(session)
    mode = _search_mode()

    assessment = RiskAssessment(
        application_id=application.id,
        analysis_kind=AnalysisKind.relative_grounds,
        knowledge_base_version=kb_version,
        # Ставится в True, только если смысловая проверка действительно
        # вызывала модель и та нашла связь.
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
    # Реестр ищет по написанию, поэтому знак-перевод не найдётся
    # по исходному обозначению. Запрос расширяется транслитерацией
    # (по правилам) и переводом (языковой моделью).
    variants = await QueryVariantGenerator(llm_provider).build(mark_text)
    job.search_strategy_json = {
        **(job.search_strategy_json or {}),
        "query_variants": [
            {"text": variant.text, "kind": variant.kind} for variant in variants
        ],
    }

    records: dict[str, Any] = {}
    found_by: dict[str, str] = {}
    try:
        for variant in variants:
            for search_type in ("exact", "fuzzy", "phonetic"):
                query = SearchQuery(
                    mark_text=variant.text,
                    mark_type=(
                        application.mark_type.value if application.mark_type else None
                    ),
                    classes=classes or None,
                    search_type=search_type,
                    max_results=MAX_RESULTS,
                )
                for record in await registry_provider.search_marks(query):
                    # Один знак может найтись несколькими видами поиска
                    # и по нескольким вариантам запроса.
                    if record.record_id not in records:
                        records[record.record_id] = record
                        found_by[record.record_id] = variant.kind
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
    scored: list[tuple[Any, Any]] = [
        (
            record,
            assess(
                applicant_mark=mark_text,
                conflicting_mark=record.mark_text,
                applicant_classes=classes,
                conflicting_classes=record.classes,
                applicant_goods=application.goods_services_raw or "",
                conflicting_goods=" ".join(str(c) for c in record.classes),
            ),
        )
        for record in records.values()
    ]

    # Смысловая проверка выполняется ДО отсечения по порогу: пара
    # «ЯБЛОКО» / «APPLE» не проходит порог по звуку и начертанию,
    # и без этого шага была бы отброшена до того, как её увидела модель.
    scored, semantic_verdicts = await _apply_semantic_layer(
        scored, mark_text, llm_provider, goods_known=bool(classes)
    )
    translated = [variant for variant in variants if variant.kind == "translation"]
    if semantic_verdicts or translated:
        assessment.llm_used = True
        assessment.model_name = next(
            (
                verdict.model_name
                for verdict in semantic_verdicts.values()
                if verdict.model_name
            ),
            getattr(llm_provider, "MODEL_NAME", None),
        )

    conflicts: list[tuple[Any, Any]] = []
    for record, similarity in scored:
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
    if semantic_verdicts:
        limitations.append(
            "Смысловое сходство части обозначений определено языковой "
            "моделью, а не расчётом по правилам. Значения слов и вывод "
            "о совпадении понятий требуют проверки специалистом."
        )
    if translated:
        limitations.append(
            "Поиск дополнительно выполнен по переводу обозначения ("
            + ", ".join(f"«{variant.text}»" for variant in translated)
            + "). Перевод предложен языковой моделью; если он неточен, "
            "часть переводных знаков могла остаться ненайденной."
        )
    elif llm_provider is None:
        limitations.append(
            "Смысловое сходство обозначений на разных языках "
            "(пункт 42 Правил № 482) не проверялось и поиск по переводу "
            "не выполнялся: языковая модель недоступна."
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
        "method": (
            "deterministic_similarity + llm_semantic"
            if semantic_verdicts
            else "deterministic_similarity"
        ),
        "semantic_checks": len(semantic_verdicts),
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

        verdict = semantic_verdicts.get(record.record_id)
        if verdict is not None:
            explanation += " " + describe(verdict, mark_text, record.mark_text or "")

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
                    "found_by": found_by.get(record.record_id, "original"),
                    "similarity": similarity.as_dict(),
                    **(
                        {"semantic_verdict": verdict.as_dict()}
                        if verdict is not None
                        else {}
                    ),
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
        semantic_checks=len(semantic_verdicts),
        mode=mode.value,
    )
    return assessment
