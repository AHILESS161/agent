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
    MarkType,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    SearchJobStatus,
    SearchMode,
    TrademarkApplicationDraft,
)
from app.agents.legal.query_variants import QueryVariantGenerator
from app.agents.legal.registry_context import (
    MAX_REGISTRY_RECORDS_FOR_LLM,
    review_registry_context,
)
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

# Контрольный поиск вне выбранных классов нужен для общеизвестных знаков и
# случаев однородности товаров из разных классов. Он выполняется только после
# основного class-first прохода и намеренно уже основного поиска.
BROAD_CONTROL_RESULTS = 20

_RISK_ORDER = {
    RiskLevel.low: 0,
    RiskLevel.medium: 1,
    RiskLevel.high: 2,
    RiskLevel.critical: 3,
}


def _search_mode() -> SearchMode:
    """Режим поиска по фактически настроенному провайдеру."""
    provider = (getattr(settings, "FIPS_PROVIDER", "mock") or "mock").lower()
    if provider == "mock":
        return SearchMode.demo
    if provider in {"rospatent_public", "fips_public", "public"}:
        return SearchMode.limited
    return SearchMode.real


def _risk_level(similarity: float, confusion_likely: bool) -> RiskLevel:
    if similarity >= 0.9 and confusion_likely:
        return RiskLevel.critical
    if confusion_likely:
        return RiskLevel.high
    if similarity >= 0.5:
        return RiskLevel.medium
    return RiskLevel.low


def _llm_risk(value: Any) -> RiskLevel | None:
    try:
        return RiskLevel(str(value))
    except (TypeError, ValueError):
        return None


def _max_risk(left: RiskLevel, right: RiskLevel | None) -> RiskLevel:
    if right is None:
        return left
    return right if _RISK_ORDER[right] > _RISK_ORDER[left] else left


def _class_priority(record: Any, classes: list[int]) -> int:
    """2 — пересечение выбранных классов, 1 — класс неизвестен, 0 — вне классов."""
    if not classes:
        return 1
    record_classes = set(record.classes or [])
    if not record_classes:
        return 1
    return 2 if set(classes) & record_classes else 0


def _llm_can_elevate(
    comment: dict[str, Any] | None,
    record: Any,
    similarity: Any,
    classes: list[int],
) -> bool:
    """Разрешить юридическому слою сохранить недооценённую правилами карточку.

    Модель не меняет коэффициенты. Она может только поднять карточку на ручную
    проверку, если назвала риск не ниже medium и имеется независимая опора:
    пересечение классов, неизвестный перечень либо заметное сходство знаков.
    """
    if not comment or comment.get("requires_attention") is not True:
        return False
    level = _llm_risk(comment.get("legal_risk"))
    if level not in {RiskLevel.medium, RiskLevel.high, RiskLevel.critical}:
        return False
    return (
        _class_priority(record, classes) > 0 and similarity.mark_similarity >= 0.15
    ) or similarity.mark_similarity >= 0.5


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

    if application.mark_type is MarkType.figurative:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "Загруженное изображение сохранено, но визуальный поиск сходных "
            "изображений по реестру пока не поддерживается."
        )
        assessment.missing_data_json = [
            "Результат специализированного визуального поиска по реестру"
        ]
        assessment.limitations_json = [
            "Текстовый поиск нельзя использовать как замену сравнению графических "
            "элементов изобразительного знака. Требуется отдельная проверка изображения."
        ]
        session.add(assessment)
        await session.flush()
        return assessment

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
            "class_source": "approved" if class_context.is_confirmed else "suggested",
            "class_context": class_context.describe(),
            "search_order": (
                ["selected_classes", "broader_registry_control"]
                if classes
                else ["broader_registry_without_classes"]
            ),
            "search_types": ["exact", "fuzzy", "phonetic"],
            "sources": ["registrations", "applications"],
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
    search_scope: dict[str, str] = {}
    search_applications = getattr(registry_provider, "search_applications", None)
    applications_checked = callable(search_applications)

    async def collect_phase(
        *,
        phase_variants: list[Any],
        phase_classes: list[int] | None,
        phase_name: str,
        registration_search_types: tuple[str, ...],
        max_results: int,
    ) -> None:
        """Собрать одну фазу, сохраняя порядок class-first в аудите."""
        for variant in phase_variants:
            for search_type in registration_search_types:
                query = SearchQuery(
                    mark_text=variant.text,
                    mark_type=(
                        application.mark_type.value if application.mark_type else None
                    ),
                    classes=phase_classes or None,
                    search_type=search_type,
                    max_results=max_results,
                )
                for record in await registry_provider.search_marks(query):
                    # Не все внешние адаптеры гарантируют серверную фильтрацию.
                    # В первой фазе дополнительно проверяем пересечение локально.
                    if (
                        phase_classes
                        and record.classes
                        and not set(phase_classes).intersection(record.classes)
                    ):
                        continue
                    if record.record_id not in records:
                        records[record.record_id] = record
                        found_by[record.record_id] = variant.kind
                        search_scope[record.record_id] = phase_name

            if applications_checked:
                application_query = SearchQuery(
                    mark_text=variant.text,
                    mark_type=(
                        application.mark_type.value if application.mark_type else None
                    ),
                    classes=phase_classes or None,
                    search_type="fuzzy",
                    max_results=max_results,
                )
                for record in await search_applications(application_query):
                    if (
                        phase_classes
                        and record.classes
                        and not set(phase_classes).intersection(record.classes)
                    ):
                        continue
                    if record.record_id not in records:
                        records[record.record_id] = record
                        found_by[record.record_id] = f"application:{variant.kind}"
                        search_scope[record.record_id] = phase_name

    try:
        await collect_phase(
            phase_variants=variants,
            phase_classes=classes or None,
            phase_name=("selected_classes" if classes else "broader_registry_without_classes"),
            registration_search_types=("exact", "fuzzy", "phonetic"),
            max_results=MAX_RESULTS,
        )
        if classes:
            # Контрольный проход выполняется после классов, только по исходному
            # написанию и с меньшим лимитом. Он не вытесняет class-first выдачу.
            await collect_phase(
                phase_variants=variants[:1],
                phase_classes=None,
                phase_name="broader_registry_control",
                registration_search_types=("exact", "fuzzy"),
                max_results=BROAD_CONTROL_RESULTS,
            )
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

    # Модель должна увидеть релевантные карточки ДО числового отсечения. Иначе
    # простой коэффициент может скрыть доминирующий элемент или сходство общего
    # впечатления, которое по пунктам 41–43 Правил № 482 оценил бы юрист.
    review_candidates = sorted(
        scored,
        key=lambda pair: (
            _class_priority(pair[0], classes),
            pair[0].status in {"registered", "pending"},
            pair[1].confusion_likely,
            pair[1].mark_similarity,
            pair[1].overall,
        ),
        reverse=True,
    )[:MAX_REGISTRY_RECORDS_FOR_LLM]

    registry_review = await review_registry_context(
        llm_provider,
        applicant_mark=mark_text,
        applicant_mark_type=(
            application.mark_type.value if application.mark_type else None
        ),
        applicant_classes=classes,
        applicant_goods=application.goods_services_raw or "",
        conflicts=review_candidates,
        provider_name=getattr(settings, "FIPS_PROVIDER", "mock"),
        search_mode=mode.value,
        class_context_description=class_context.describe(),
        classes_confirmed=class_context.is_confirmed,
        applicant_details={
            "description_of_mark": application.description_of_mark,
            "transliteration": application.transliteration,
            "translation": application.translation,
            "colors_claimed": application.colors_claimed,
            "priority_claim": application.priority_claim,
        },
    )
    if registry_review is not None:
        assessment.llm_used = True
        assessment.model_name = getattr(llm_provider, "MODEL_NAME", None)

    conflicts: list[tuple[Any, Any]] = []
    llm_elevated: set[str] = set()
    for record, similarity in scored:
        comment = (
            registry_review.comments.get(record.record_id)
            if registry_review is not None
            else None
        )
        elevated = _llm_can_elevate(comment, record, similarity, classes)
        if similarity.overall < MIN_SIMILARITY and not elevated:
            continue
        if elevated and similarity.overall < MIN_SIMILARITY:
            llm_elevated.add(record.record_id)

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

    def effective_level(pair: tuple[Any, Any]) -> RiskLevel:
        record, similarity = pair
        deterministic = _risk_level(similarity.overall, similarity.confusion_likely)
        comment = (
            registry_review.comments.get(record.record_id)
            if registry_review is not None
            else None
        )
        if _llm_can_elevate(comment, record, similarity, classes):
            return _max_risk(deterministic, _llm_risk(comment.get("legal_risk")))
        return deterministic

    conflicts.sort(
        key=lambda pair: (
            _RISK_ORDER[effective_level(pair)],
            _class_priority(pair[0], classes),
            pair[1].overall,
        ),
        reverse=True,
    )

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
    elif mode is SearchMode.limited:
        limitations.append(
            "Поиск выполнен через публичный интерфейс Поисковой платформы Роспатента. "
            "Это недокументированный интерфейс с ограниченной полнотой и без гарантии "
            "стабильности; результат является предварительным."
        )
    if applications_checked:
        limitations.append(
            "Проверены зарегистрированные обозначения и опубликованные заявки из доступных "
            "наборов провайдера. Общеизвестные знаки, НМПТ, фирменные наименования и "
            "объекты по пунктам 7–10 статьи 1483 требуют отдельных поисков."
        )
    else:
        limitations.append(
            "Проверены только зарегистрированные обозначения: выбранный провайдер не "
            "поддерживает поиск опубликованных заявок."
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
    if registry_review is not None:
        limitations.append(
            "Языковой модели до порогового отсечения переданы приоритетные записи "
            "реестра (не более "
            f"{MAX_REGISTRY_RECORDS_FOR_LLM}) для пояснения факторов риска. "
            "Модель не изменяет рассчитанные системой коэффициенты, но может поднять "
            "карточку на ручную проверку при наличии независимых признаков."
        )
    if application.mark_type is MarkType.combined:
        limitations.append(
            "Для комбинированного знака выполнен поиск по подтверждённым словесным "
            "элементам. Сходство графики и общего визуального впечатления по изображениям "
            "реестра автоматически не проверялось."
        )

    missing: list[str] = []
    if not classes:
        missing.append("Перечень классов МКТУ")

    assessment.limitations_json = limitations
    assessment.missing_data_json = missing
    assessment.sources_used_json = [
        f"registry:{record.record_id}" for record, _ in conflicts
    ]
    methods = ["deterministic_similarity"]
    if semantic_verdicts:
        methods.append("llm_semantic")
    if registry_review is not None:
        methods.append("llm_registry_review")
    assessment.verification_json = {
        "records_examined": len(records),
        "conflicts_found": len(conflicts),
        "method": " + ".join(methods),
        "semantic_checks": len(semantic_verdicts),
        "llm_registry_records_sent": (
            len(review_candidates)
            if registry_review is not None
            else 0
        ),
        "llm_registry_review": (
            registry_review.as_dict() if registry_review is not None else None
        ),
        "applications_checked": applications_checked,
        "class_first_search": bool(classes),
        "selected_class_records": sum(
            scope == "selected_classes" for scope in search_scope.values()
        ),
        "broader_control_records": sum(
            scope == "broader_registry_control" for scope in search_scope.values()
        ),
        "llm_elevated_record_ids": sorted(llm_elevated),
        "criteria": (
            "пп.40–45 Правил № 482; п.6 ст.1483 ГК РФ; "
            "п.162 Постановления Пленума ВС РФ № 10"
        ),
    }

    if not conflicts:
        assessment.overall_risk = None
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "По словесным элементам не найдено достаточных совпадений; визуальное "
            "сходство комбинированного знака не проверено."
            if application.mark_type is MarkType.combined
            else "В доступной выдаче не выявлены карточки, достаточные для вывода о риске."
        )
        assessment.summary = (
            f"По обозначению «{mark_text}» значимые совпадения в доступной выдаче "
            "не выявлены. Это не означает отсутствие риска: поиск ограничен "
            "доступными источниками и требует проверки специалистом."
        )
        session.add(assessment)
        await session.flush()
        return assessment

    highest_record, highest = conflicts[0]
    assessment.overall_risk = effective_level(conflicts[0])
    assessment.summary = (
        f"Выявлено карточек, требующих оценки: {len(conflicts)}. Наиболее значимая — "
        f"«{highest_record.mark_text}» (расчётный коэффициент {highest.overall:.2f}, "
        f"предварительный риск {assessment.overall_risk.value})."
    )
    if registry_review is not None and registry_review.summary:
        assessment.summary += f" Комментарий LLM: {registry_review.summary}"
    if application.mark_type is MarkType.combined:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "Текстовая часть комбинированного знака проверена; визуальное сходство "
            "изображений требует отдельной проверки."
        )
        assessment.missing_data_json = list(assessment.missing_data_json or []) + [
            "Результат специализированного визуального поиска по реестру"
        ]
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

        registry_comment = (
            registry_review.comments.get(record.record_id)
            if registry_review is not None
            else None
        )
        if registry_comment and registry_comment.get("comment"):
            explanation += " Комментарий LLM по записи реестра: " + str(
                registry_comment["comment"]
            )
        if registry_comment:
            for title, key in (
                ("Сходство обозначений", "mark_similarity_analysis"),
                ("Однородность товаров/услуг", "goods_homogeneity_analysis"),
                ("Приоритет и статус", "priority_and_status_analysis"),
            ):
                if registry_comment.get(key):
                    explanation += f" {title}: {registry_comment[key]}"
            if registry_comment.get("counterarguments"):
                explanation += " Контраргументы: " + "; ".join(
                    registry_comment["counterarguments"]
                ) + "."
            if registry_comment.get("missing_evidence"):
                explanation += " Не хватает данных: " + "; ".join(
                    registry_comment["missing_evidence"]
                ) + "."

        finding_level = effective_level((record, similarity))

        session.add(
            RiskFinding(
                assessment_id=assessment.id,
                category="conflicting_mark",
                level=finding_level,
                legal_basis="ГК РФ ст. 1483 п. 6",
                explanation=explanation,
                case_facts_json=[
                    f"Заявляемое обозначение: {mark_text}",
                    f"Классы МКТУ: {', '.join(map(str, classes)) or 'не определены'}",
                    f"Противопоставленный знак: {record.record_id}",
                ],
                missing_data_json=[],
                confidence=round(
                    min(
                        0.9,
                        max(
                            similarity.overall,
                            registry_review.confidence
                            if registry_review is not None
                            and registry_review.confidence is not None
                            else 0.0,
                        ),
                    ),
                    2,
                ),
                recommended_action=(
                    str(registry_comment.get("recommended_action"))
                    if registry_comment and registry_comment.get("recommended_action")
                    else (
                        "Оценить вероятность смешения и рассмотреть получение "
                        "письма-согласия либо доработку обозначения"
                        if similarity.confusion_likely
                        else "Принять во внимание при итоговой оценке"
                    )
                ),
                # Источник — запись реестра, а не фрагмент базы знаний,
                # поэтому цитаты из нормативных материалов здесь нет.
                citations_verified=False,
                verification_json={
                    "source": "registry_record",
                    "record_id": record.record_id,
                    # Данные карточки сохраняются вместе с юридическим выводом.
                    # Фронтенду не приходится восстанавливать знак, классы и
                    # статус из технического текста explanation или выполнять
                    # второй, потенциально уже изменившийся поиск в реестре.
                    "registry_record": {
                        "record_id": record.record_id,
                        "mark_text": record.mark_text,
                        "owner": record.owner,
                        "classes": record.classes,
                        "status": record.status,
                        "source": record.source,
                        "application_number": record.application_number,
                        "registration_number": record.registration_number,
                        "filing_date": record.filing_date,
                        "registration_date": record.registration_date,
                    },
                    "found_by": found_by.get(record.record_id, "original"),
                    "search_scope": search_scope.get(record.record_id),
                    "similarity": similarity.as_dict(),
                    "decision_source": (
                        "llm_legal_attention"
                        if record.record_id in llm_elevated
                        else "deterministic_threshold"
                    ),
                    "effective_risk": finding_level.value,
                    **(
                        {"semantic_verdict": verdict.as_dict()}
                        if verdict is not None
                        else {}
                    ),
                    **(
                        {"llm_registry_review": registry_comment}
                        if registry_comment is not None
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
