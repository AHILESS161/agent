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
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.classification.rag_class_analyzer import RagNiceClassAnalyzer
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    ItemSource,
    NiceCategory,
    NiceClassSuggestion,
    TrademarkApplicationDraft,
)
from app.infrastructure.rag.store import load_active_chunks

logger = get_logger(__name__)

_CATEGORY_MAP = {
    "primary": NiceCategory.primary,
    "secondary": NiceCategory.secondary,
    "borderline": NiceCategory.borderline,
}


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
        parts = []
        for item in self.effective:
            description = (item.class_description or "").strip()
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
) -> dict[str, Any]:
    """Подобрать классы МКТУ и сохранить предложения.

    Уже подтверждённые специалистом классы не затрагиваются: повторный
    подбор не должен отменять его решение.
    """
    chunks = await load_active_chunks(session)
    if not chunks:
        return {
            "status": "inconclusive",
            "reason": (
                "База знаний пуста. Выполните: python -m scripts.ingest_knowledge"
            ),
            "suggestions": [],
        }

    analyzer = RagNiceClassAnalyzer(llm_provider, chunks)
    outcome = await analyzer.analyse(
        {
            "mark_text": application.mark_text or application.mark_name,
            "business_description": application.business_description,
            "goods_services": application.goods_services_raw,
        }
    )

    if not outcome.is_conclusive:
        return {
            "status": "inconclusive",
            "reason": outcome.reason,
            "suggestions": [],
            # Неподтверждённые предложения — не результат, но и не мусор:
            # специалист вправе принять их под свою ответственность.
            "unverified": outcome.verification.get("rejected", []),
            "verification": outcome.verification,
        }

    existing = await load_class_context(session, application.id)
    approved_numbers = {item.class_number for item in existing.approved}

    # Неподтверждённые предложения заменяем: они устарели.
    for stale in existing.suggested:
        await session.delete(stale)
    await session.flush()

    created: list[dict[str, Any]] = []
    for suggestion in outcome.result.suggestions:
        if suggestion.class_number in approved_numbers:
            # Решение специалиста по этому классу уже есть.
            continue
        record = NiceClassSuggestion(
            application_id=application.id,
            class_number=suggestion.class_number,
            class_description="; ".join(suggestion.goods_services) or None,
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
