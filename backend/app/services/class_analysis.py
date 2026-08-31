"""Подбор классов МКТУ и передача их в оценку оснований отказа.

Почему это связано. Различительная способность оценивается только
применительно к конкретным товарам: «ЯБЛОКО» для свежих фруктов
описательно, для компьютеров — произвольно. Значит, перечень классов
влияет на вывод об охраноспособности, и оценка оснований должна
опираться на него, а не на общее описание деятельности.

Отсюда правило: если классы не подтверждены специалистом, вывод об
основаниях сделан на неподтверждённом входе, и это прямо указывается
в ограничениях анализа.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.classification.rag_class_analyzer import (
    ClassSuggestion,
    RagNiceClassAnalyzer,
)
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    ItemSource,
    NiceCategory,
    NiceClassSuggestion,
    TrademarkApplicationDraft,
)
from app.infrastructure.rag.store import load_active_chunks
from app.services.nice_catalog import load_catalog, search as search_nice_catalog

logger = get_logger(__name__)

_CATEGORY_MAP = {
    "primary": NiceCategory.primary,
    "secondary": NiceCategory.secondary,
    "borderline": NiceCategory.borderline,
}

_REPAIR_RE = re.compile(
    r"\b(ремонт\w*|почин\w*|тех(?:ническ\w*)?\s*обслужив\w*|"
    r"установк\w*|монтаж\w*)\b",
    re.IGNORECASE,
)
_GOODS_ACTIVITY_RE = re.compile(
    r"\b(продаж\w*|прода\w*|торгов\w*|производ\w*|изготов\w*|поставк\w*|"
    r"магазин\w*|товар\w*)\b",
    re.IGNORECASE,
)


def _service_intent(text: str) -> tuple[set[int], bool]:
    """Вернуть обязательные сервисные классы и признак чистой услуги.

    Название ремонтируемого устройства не превращает услугу ремонта в
    заявление самого устройства как товара. Для ремонта, установки и
    технического обслуживания оборудования основной класс — 37.
    """
    normalized = " ".join((text or "").split())
    if not _REPAIR_RE.search(normalized):
        return set(), False
    return {37}, not bool(_GOODS_ACTIVITY_RE.search(normalized))


def _apply_service_intent(
    suggestions: list[ClassSuggestion], source_text: str
) -> list[ClassSuggestion]:
    required, service_only = _service_intent(source_text)
    if service_only:
        suggestions = [item for item in suggestions if item.class_number >= 35]

    by_number = {item.class_number: item for item in suggestions}
    for number in required:
        if number in by_number:
            continue
        by_number[number] = ClassSuggestion(
            class_number=number,
            rationale=(
                "Заявлена услуга ремонта, установки или технического обслуживания; "
                "такие работы относятся к классу 37."
            ),
            category="primary",
            # Пользователю и заявлению нужен конкретный заявляемый перечень,
            # а не полный заголовок класса 37 со строительством и бурением.
            goods_services=[" ".join(source_text.split()) or "услуги ремонта"],
            confidence=0.95,
            citations=[],
        )
    return list(by_number.values())


@dataclass
class ClassContext:
    """Классы дела для передачи в оценку оснований."""

    approved: list[NiceClassSuggestion]
    suggested: list[NiceClassSuggestion]

    @property
    def effective(self) -> list[NiceClassSuggestion]:
        """Подтверждённые классы приоритетнее предложенных."""
        return self.approved or self.suggested

    @property
    def is_confirmed(self) -> bool:
        """Классы подтверждены специалистом."""
        return bool(self.approved)

    @property
    def has_any(self) -> bool:
        return bool(self.effective)

    def describe(self) -> str:
        """Текст для промпта: классы с отнесёнными к ним товарами."""
        if not self.has_any:
            return "не определены"
        catalog_by_number = {item.number: item for item in load_catalog()}
        parts = []
        for item in self.effective:
            description = (item.class_description or "").strip()
            catalog_item = catalog_by_number.get(item.class_number)
            if catalog_item and description == catalog_item.full_description:
                description = (
                    f"{catalog_item.description} Заявляется полный официальный "
                    f"перечень класса ({len(catalog_item.items)} позиций)."
                )
            elif len(description) > 2_000:
                # Ручной длинный перечень не должен занять весь контекст LLM.
                # Полный текст остаётся в DOCX и расчёте пошлины.
                description = description[:2_000].rstrip() + "…"
            parts.append(
                f"класс {item.class_number}"
                + (f" ({description})" if description else "")
            )
        return "; ".join(parts)

    def as_numbers(self) -> list[int]:
        return [item.class_number for item in self.effective]


async def load_class_context(
    session: AsyncSession, application_id: int
) -> ClassContext:
    """Загрузить классы дела, разделив подтверждённые и предложенные."""
    rows = (
        (
            await session.execute(
                select(NiceClassSuggestion)
                .where(NiceClassSuggestion.application_id == application_id)
                .order_by(NiceClassSuggestion.class_number)
            )
        )
        .scalars()
        .all()
    )
    return ClassContext(
        approved=[r for r in rows if r.approved is True],
        suggested=[r for r in rows if r.approved is not True],
    )


async def run_class_analysis(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    llm_provider: Any,
    *,
    preserve_approved: bool = True,
) -> dict[str, Any]:
    """Подобрать классы МКТУ и сохранить предложения.

    Уже подтверждённые специалистом классы не затрагиваются: повторный
    подбор не должен отменять его решение.
    """
    chunks = await load_active_chunks(session)
    if not chunks:
        return await _catalog_fallback(
            session,
            application,
            "Языковая модель или база знаний недоступна",
            preserve_approved=preserve_approved,
        )

    analyzer = RagNiceClassAnalyzer(llm_provider, chunks)
    outcome = await analyzer.analyse(
        {
            "mark_text": application.mark_text or application.mark_name,
            "business_description": application.business_description,
            "goods_services": application.goods_services_raw,
        }
    )

    if not outcome.is_conclusive:
        return await _catalog_fallback(
            session,
            application,
            outcome.reason,
            preserve_approved=preserve_approved,
        )

    source_text = " ".join(
        part for part in (
            application.goods_services_raw or "",
            application.business_description or "",
        ) if part.strip()
    )
    outcome.result.suggestions = _apply_service_intent(
        outcome.result.suggestions,
        source_text,
    )

    existing = await load_class_context(session, application.id)
    approved_numbers = (
        {item.class_number for item in existing.approved}
        if preserve_approved
        else set()
    )

    # При обычном автоматическом подборе решение человека сохраняем. Явная
    # команда «Подобрать заново» заменяет весь список, включая подтверждённые
    # ранее классы: пользователь ожидает чистый результат по новым данным.
    stale_rows = (
        existing.suggested
        if preserve_approved
        else [*existing.approved, *existing.suggested]
    )
    for stale in stale_rows:
        await session.delete(stale)
    await session.flush()

    created: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    catalog_by_number = {item.number: item for item in load_catalog()}
    for suggestion in outcome.result.suggestions:
        if suggestion.class_number in seen_numbers:
            continue
        seen_numbers.add(suggestion.class_number)
        if suggestion.class_number in approved_numbers:
            # Решение специалиста по этому классу уже есть.
            continue
        record = NiceClassSuggestion(
            application_id=application.id,
            class_number=suggestion.class_number,
            # По умолчанию заявление охватывает полный официальный перечень
            # позиций класса. Заголовок класса — лишь краткое описание и не
            # заменяет перечень товаров/услуг в заявлении.
            class_description=(
                catalog_by_number.get(suggestion.class_number).full_description
                if catalog_by_number.get(suggestion.class_number)
                else "; ".join(suggestion.goods_services)
            ) or None,
            rationale=suggestion.rationale,
            confidence=suggestion.confidence,
            category=_CATEGORY_MAP.get(suggestion.category, NiceCategory.borderline),
            approved=None,
        )
        session.add(record)
        created.append(
            {
                "class_number": suggestion.class_number,
                "category": suggestion.category,
                "confidence": suggestion.confidence,
                "goods_services": suggestion.goods_services,
                "rationale": suggestion.rationale,
                "citations": suggestion.citations,
            }
        )

    await session.flush()
    logger.info(
        "Подбор классов МКТУ выполнен",
        application_id=application.id,
        suggested=len(created),
        already_approved=len(approved_numbers),
    )

    return {
        "status": "ok",
        "summary": outcome.result.summary,
        "suggestions": created,
        "already_approved": sorted(approved_numbers),
        "unclassified": outcome.result.unclassified,
        "limitations": outcome.result.limitations,
        "verification": outcome.verification,
        "requires_specialist_review": True,
        "notice": (
            "Классы предложены автоматически и требуют подтверждения. "
            "От перечня классов зависит вывод об охраноспособности "
            "обозначения."
        ),
    }


async def _catalog_fallback(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    reason: str,
    *,
    preserve_approved: bool = True,
) -> dict[str, Any]:
    """Детерминированный резерв: классы не должны исчезать вместе с LLM.

    Справочник ищет русские слова по заголовкам и составу классов. Результат
    остаётся предложением и обязательно подтверждается человеком.
    """
    logger.warning(
        "Использован резервный подбор классов МКТУ",
        application_id=application.id,
        reason=reason,
    )
    source_parts = [
        part for part in (
            application.goods_services_raw or "",
            application.business_description or "",
        ) if part.strip()
    ]
    raw_phrases = [
        p.strip() for part in source_parts
        for p in re.split(r"[;,\n]+", part)
        if len(p.strip()) >= 3
    ]
    # После объединения клиентских полей одно описание намеренно хранится
    # в business_description и goods_services_raw. Не ищем его дважды.
    phrases: list[str] = []
    seen_phrases: set[str] = set()
    for phrase in raw_phrases:
        key = phrase.casefold()
        if key not in seen_phrases:
            seen_phrases.add(key)
            phrases.append(phrase)

    found = {}
    for phrase in phrases[:20]:
        required_service_classes, service_only = _service_intent(phrase)
        for number in required_service_classes:
            item = next((entry for entry in load_catalog() if entry.number == number), None)
            if item:
                found.setdefault(number, (item, phrase))
        if service_only:
            continue
        # Второе совпадение часто основано на одном общем слове. Например,
        # у «ремонта бытовой техники» после правильного класса 37 шёл класс
        # 16 лишь из-за слов «бытовой клей». Для автоматического предложения
        # оставляем только наиболее релевантный класс каждой позиции.
        for item in search_nice_catalog(phrase, limit=1):
            found.setdefault(item.number, (item, phrase))
            if len(found) >= 6:
                break
        if len(found) >= 6:
            break

    # Торговля — самостоятельная услуга класса 35, но не подразумевается
    # автоматически при упоминании любого товара. Добавляем её только когда
    # пользователь прямо написал о продаже, магазине или продвижении.
    if re.search(
        r"\b(продаж\w*|прода\w*|торгов\w*|магазин\w*|маркетплейс\w*|реклам\w*|продвижен\w*)\b",
        " ".join(source_parts),
        flags=re.IGNORECASE,
    ):
        trade_class = next((item for item in load_catalog() if item.number == 35), None)
        if trade_class:
            found.setdefault(
                trade_class.number,
                (trade_class, "продажа и продвижение товаров"),
            )

    if not found:
        return {"status": "inconclusive", "reason": reason, "suggestions": []}

    existing = await load_class_context(session, application.id)
    approved_numbers = (
        {item.class_number for item in existing.approved}
        if preserve_approved
        else set()
    )
    stale_rows = (
        existing.suggested
        if preserve_approved
        else [*existing.approved, *existing.suggested]
    )
    for stale in stale_rows:
        await session.delete(stale)
    await session.flush()

    created = []
    for number, (item, phrase) in found.items():
        if number in approved_numbers:
            continue
        record = NiceClassSuggestion(
            application_id=application.id,
            class_number=number,
            # Пока клиент явно не сузил перечень, используем полный
            # официальный перечень позиций выбранного класса.
            class_description=item.full_description,
            rationale=f"Справочник МКТУ: найдено по описанию «{phrase}».",
            confidence=0.55,
            category=NiceCategory.primary,
            approved=None,
        )
        session.add(record)
        created.append({
            "class_number": number,
            "category": "primary",
            "confidence": 0.55,
            "goods_services": [phrase],
            "rationale": record.rationale,
            "citations": [],
        })
    await session.flush()
    return {
        "status": "catalog",
        "summary": "Классы подобраны по актуальному официальному справочнику МКТУ.",
        "reason": reason,
        "suggestions": created,
        "already_approved": sorted(approved_numbers),
        "requires_specialist_review": True,
        "notice": "Проверьте и подтвердите каждый предложенный класс.",
    }
