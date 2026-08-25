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

import asyncio
import time
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
from app.agents.legal.query_variants import QueryVariantGenerator, deterministic_variants
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
from app.document_processing.similarity import assess, with_image_visual, with_semantic
from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.rag.store import knowledge_base_version
from app.services.class_analysis import load_class_context
from app.services.visual_mark_similarity import (
    MAX_VISUAL_IMAGE_CHECKS,
    applicant_image,
    compare_registry_candidates,
)

logger = get_logger(__name__)

# Сколько записей запрашивать у провайдера на один вид поиска.
MAX_RESULTS = 40

# Порог, ниже которого совпадение не сохраняется как конфликт.
MIN_SIMILARITY = 0.3

# Потолок на число обращений к модели за один поиск. Смысловая проверка
# идёт по парам, и без ограничения большая выдача обошлась бы дорого;
# пары берутся в порядке убывания однородности товаров — там смысловое
# совпадение опаснее всего.
MAX_SEMANTIC_CHECKS = 4

# Контрольный поиск вне выбранных классов нужен для общеизвестных знаков и
# случаев однородности товаров из разных классов. Он выполняется только после
# основного class-first прохода и намеренно уже основного поиска.
BROAD_CONTROL_RESULTS = 12

# Публичный поиск не имеет гарантированного SLA. Сначала тратим бюджет на
# выбранные классы, а общий контроль выполняем только на оставшемся времени.
REGISTRY_SEARCH_BUDGET_SECONDS = 25.0
# Это дополнительный текстовый разбор. Поиск, class-first ранжирование и
# смысловая оценка карточек уже выполнены, поэтому долго ждать его нет смысла.
REGISTRY_REVIEW_BUDGET_SECONDS = 4.0
REGISTRY_SEARCH_CONCURRENCY = 4
QUERY_VARIANT_BUDGET_SECONDS = 4.0
SEMANTIC_LAYER_BUDGET_SECONDS = 8.0
VISUAL_COMPARISON_BUDGET_SECONDS = 8.0

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

    async def analyze_one(index: int) -> tuple[int, SemanticVerdict]:
        record, _ = updated[index]
        return index, await analyzer.analyze(mark_text, record.mark_text or "")

    results = await asyncio.gather(*(analyze_one(index) for index in candidates))
    for index, verdict in results:
        record, similarity = updated[index]
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
    query_variants_timed_out = False
    try:
        variants = await asyncio.wait_for(
            QueryVariantGenerator(llm_provider).build(mark_text),
            timeout=QUERY_VARIANT_BUDGET_SECONDS,
        )
    except TimeoutError:
        variants = deterministic_variants(mark_text)
        query_variants_timed_out = True
        logger.warning(
            "Расширение поискового запроса остановлено по лимиту времени",
            seconds=QUERY_VARIANT_BUDGET_SECONDS,
        )
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
    search_errors: list[str] = []
    search_complete = True
    search_semaphore = asyncio.Semaphore(REGISTRY_SEARCH_CONCURRENCY)

    async def collect_phase(
        *,
        phase_variants: list[Any],
        phase_classes: list[int] | None,
        phase_name: str,
        registration_search_types: tuple[str, ...],
        max_results: int,
        timeout_seconds: float,
    ) -> bool:
        """Собрать одну фазу, сохраняя порядок class-first в аудите."""
        calls: list[tuple[int, Any, str, SearchQuery, Any]] = []
        call_index = 0
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
                calls.append(
                    (call_index, variant, "registration", query, registry_provider.search_marks)
                )
                call_index += 1

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
                calls.append(
                    (call_index, variant, "application", application_query, search_applications)
                )
                call_index += 1

        async def execute(call: tuple[int, Any, str, SearchQuery, Any]):
            index, variant, source, query, searcher = call
            async with search_semaphore:
                return index, variant, source, await searcher(query)

        tasks = [asyncio.create_task(execute(call)) for call in calls]
        done, pending = await asyncio.wait(tasks, timeout=max(0.1, timeout_seconds))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            search_errors.append(
                f"{phase_name}: не завершено запросов {len(pending)} из {len(tasks)}"
            )

        completed: list[tuple[int, Any, str, list[Any]]] = []
        for task in done:
            try:
                completed.append(task.result())
            except Exception as exc:  # один сбой публичного поиска не обнуляет остальные
                search_errors.append(f"{phase_name}: {type(exc).__name__}: {exc}")

        for _, variant, source, found in sorted(completed, key=lambda item: item[0]):
            for record in found:
                # Не все внешние адаптеры гарантируют серверную фильтрацию.
                if (
                    phase_classes
                    and record.classes
                    and not set(phase_classes).intersection(record.classes)
                ):
                    continue
                if record.record_id not in records:
                    records[record.record_id] = record
                    found_by[record.record_id] = (
                        f"application:{variant.kind}"
                        if source == "application"
                        else variant.kind
                    )
                    search_scope[record.record_id] = phase_name
        return not pending and len(completed) == len(tasks)

    try:
        search_deadline = time.monotonic() + REGISTRY_SEARCH_BUDGET_SECONDS
        # В публичном адаптере phonetic отправляется как тот же fuzzy-запрос.
        # Фонетическая близость всё равно рассчитывается локально по карточкам.
        registration_types = (
            ("exact", "fuzzy")
            if mode is SearchMode.limited
            else ("exact", "fuzzy", "phonetic")
        )
        search_complete = await collect_phase(
            phase_variants=variants,
            phase_classes=classes or None,
            phase_name=("selected_classes" if classes else "broader_registry_without_classes"),
            registration_search_types=registration_types,
            max_results=MAX_RESULTS,
            timeout_seconds=REGISTRY_SEARCH_BUDGET_SECONDS,
        )
        remaining = search_deadline - time.monotonic()
        if classes and remaining >= 5:
            # Контрольный проход выполняется после классов, только по исходному
            # написанию и с меньшим лимитом. Он не вытесняет class-first выдачу.
            search_complete = (
                await collect_phase(
                    phase_variants=variants[:1],
                    phase_classes=None,
                    phase_name="broader_registry_control",
                    registration_search_types=("exact", "fuzzy"),
                    max_results=BROAD_CONTROL_RESULTS,
                    timeout_seconds=remaining,
                )
                and search_complete
            )
        elif classes:
            search_complete = False
            search_errors.append("broader_registry_control: пропущен из-за лимита времени")
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
    semantic_layer_timed_out = False
    try:
        scored, semantic_verdicts = await asyncio.wait_for(
            _apply_semantic_layer(
                scored, mark_text, llm_provider, goods_known=bool(classes)
            ),
            timeout=SEMANTIC_LAYER_BUDGET_SECONDS,
        )
    except TimeoutError:
        semantic_verdicts = {}
        semantic_layer_timed_out = True
        logger.warning(
            "Смысловое сравнение обозначений остановлено по лимиту времени",
            seconds=SEMANTIC_LAYER_BUDGET_SECONDS,
        )
    visual_comparisons: dict[str, Any] = {}
    visual_errors: list[str] = []
    if application.mark_type is MarkType.combined and application.mark_image_file_id:
        source_image = await applicant_image(session, application)
        if source_image:
            visual_candidates = [
                record
                for record, _ in sorted(
                    scored,
                    key=lambda pair: (
                        _class_priority(pair[0], classes),
                        pair[0].status in {"registered", "pending"},
                        pair[1].mark_similarity,
                    ),
                    reverse=True,
                )
                if record.image_url
            ][:MAX_VISUAL_IMAGE_CHECKS]
            try:
                visual_comparisons, visual_errors = await asyncio.wait_for(
                    compare_registry_candidates(
                        source_image, visual_candidates, registry_provider
                    ),
                    timeout=VISUAL_COMPARISON_BUDGET_SECONDS,
                )
            except TimeoutError:
                visual_comparisons = {}
                visual_errors = [
                    "Визуальное сравнение остановлено по лимиту времени"
                ]
                logger.warning(
                    "Визуальное сравнение карточек остановлено по лимиту времени",
                    seconds=VISUAL_COMPARISON_BUDGET_SECONDS,
                )
            scored = [
                (
                    record,
                    with_image_visual(similarity, visual_comparisons[record.record_id].score)
                    if record.record_id in visual_comparisons
                    else similarity,
                )
                for record, similarity in scored
            ]
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

    registry_review_timed_out = False
    try:
        registry_review = await asyncio.wait_for(
            review_registry_context(
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
                    "visual_records_compared": len(visual_comparisons),
                    "visual_comparison_method": (
                        "dhash+ahash+color_histogram+aspect_ratio"
                        if visual_comparisons
                        else None
                    ),
                },
            ),
            timeout=REGISTRY_REVIEW_BUDGET_SECONDS,
        )
    except TimeoutError:
        registry_review = None
        registry_review_timed_out = True
        logger.warning(
            "LLM-разбор карточек реестра остановлен по лимиту времени",
            seconds=REGISTRY_REVIEW_BUDGET_SECONDS,
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
    if query_variants_timed_out:
        limitations.append(
            "Поиск по исходному написанию и транслитерации выполнен, но модель не успела "
            "предложить перевод обозначения в установленный срок."
        )
    if semantic_layer_timed_out:
        limitations.append(
            "Смысловое сравнение обозначений на разных языках не завершилось в установленный срок; "
            "найденные карточки ранжированы по воспроизводимым текстовым показателям."
        )
    if not search_complete:
        limitations.append(
            "Часть контрольных запросов к публичному реестру не завершилась в установленный срок. "
            "Результаты поиска внутри выбранных классов сохранены; для окончательного решения рекомендуется повторная проверка."
        )
    if registry_review_timed_out:
        limitations.append(
            "Дополнительный комментарий языковой модели по карточкам реестра не сформирован в установленный срок. "
            "Рассчитанные показатели сходства и найденные карточки сохранены."
        )
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
    if application.mark_type is MarkType.combined and visual_comparisons:
        limitations.append(
            "Для комбинированного знака изображения доступных карточек были "
            "предварительно сопоставлены по форме, яркостной структуре, цветам и "
            "соотношению сторон. Это первичное ранжирование, а не заключение эксперта."
        )
    elif application.mark_type is MarkType.combined:
        limitations.append(
            "Для комбинированного знака выполнен поиск по подтверждённым словесным "
            "элементам. Сходство графики и общего визуального впечатления по изображениям "
            "реестра автоматически не проверялось."
        )

    missing: list[str] = []
    if not classes:
        missing.append("Перечень классов МКТУ")
    if application.mark_type is MarkType.combined and not visual_comparisons:
        missing.append("Изображения карточек для визуального сопоставления")

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
        "search_complete": search_complete,
        "search_errors": search_errors[:10],
        "query_variants_timed_out": query_variants_timed_out,
        "semantic_layer_timed_out": semantic_layer_timed_out,
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
        "visual_records_available": sum(bool(record.image_url) for record in records.values()),
        "visual_records_compared": len(visual_comparisons),
        "visual_comparison_errors": visual_errors[:10],
        "visual_comparison_method": (
            "dhash+ahash+color_histogram+aspect_ratio"
            if visual_comparisons
            else None
        ),
    }

    if not conflicts:
        assessment.overall_risk = None
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "По словесным элементам не найдено достаточных совпадений; визуальное "
            "сходство комбинированного знака не проверено."
            if application.mark_type is MarkType.combined and not visual_comparisons
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
    risk_wording = {
        RiskLevel.low: "не выглядит препятствием для регистрации",
        RiskLevel.medium: "требует дополнительной правовой оценки",
        RiskLevel.high: "может создать существенный риск отказа",
        RiskLevel.critical: "создаёт высокий риск отказа",
    }[assessment.overall_risk]
    class_wording = (
        "классах " + ", ".join(str(value) for value in classes)
        if classes
        else "доступной части реестра"
    )
    assessment.summary = (
        f"Поиск в {class_wording} завершён. Для сравнения отобрано "
        f"{len(conflicts)} обозначений. Наиболее близкое — "
        f"«{highest_record.mark_text}»; по предварительной оценке оно "
        f"{risk_wording}."
    )
    if application.mark_type is MarkType.combined and not visual_comparisons:
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
        level = effective_level((record, similarity))
        if level is RiskLevel.low:
            legal_assessment = (
                "Словесные элементы и общий смысл обозначений различаются. "
                "Даже при пересечении отдельных товаров или услуг очевидной "
                "вероятности смешения предварительно не установлено."
            )
        elif level is RiskLevel.medium:
            legal_assessment = (
                "Есть отдельные сходные элементы и пересечение товаров или услуг. "
                "Перед подачей нужно подробнее сопоставить перечни и общее "
                "впечатление от обозначений."
            )
        else:
            legal_assessment = (
                "Сходные элементы сочетаются с пересечением товаров или услуг, "
                "поэтому Роспатент может увидеть вероятность смешения обозначений."
            )
        explanation = (
            f"Заявляемое обозначение «{mark_text}» сопоставлено с "
            f"«{record.mark_text}» (правообладатель: "
            f"{record.owner or 'в открытой записи не указан'}). {legal_assessment}"
        )
        image_comparison = visual_comparisons.get(record.record_id)
        if image_comparison is not None:
            explanation += (
                " Изображения также сопоставлены автоматически; этот результат "
                "используется как подсказка и требует визуальной проверки."
            )

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
                        "image_url": record.image_url,
                    },
                    "image_comparison": (
                        image_comparison.as_dict() if image_comparison else None
                    ),
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
