"""Полнота подбора классов МКТУ.

Пропустить класс дороже, чем предложить лишний: после подачи заявки
класс не добавить — нужна новая заявка и новая пошлина. Специалист
лишнее уберёт сам.
"""

from __future__ import annotations

import pytest

from app.agents.classification.rag_class_analyzer import (
    ALWAYS_INCLUDE_CLASSES,
    RagNiceClassAnalyzer,
    SYSTEM_PROMPT,
)
from app.infrastructure.rag.store import StoredChunk


def _chunk(chunk_id: int, anchor: str, content: str) -> StoredChunk:
    return StoredChunk(
        chunk_id=chunk_id,
        source_id=1,
        source_name="МКТУ",
        source_version="1",
        source_type="methodology",
        content=content,
        anchor=anchor,
        article=None,
        clause=None,
    )


@pytest.fixture
def corpus() -> list[StoredChunk]:
    return [
        _chunk(1, "Классы товаров → Класс 25. Одежда и обувь", "Одежда; обувь."),
        _chunk(2, "Классы товаров → Класс 28. Игры", "Игры, игрушки."),
        _chunk(
            3,
            "Классы услуг → Класс 35. Реклама и торговля",
            "Реклама; услуги розничной и оптовой торговли.",
        ),
    ]


class TestTradeServicesAlwaysOffered:
    """Класс 35 нужен почти любому, кто продаёт, в том числе онлайн."""

    def test_trade_class_is_declared(self):
        assert any("35" in marker for marker in ALWAYS_INCLUDE_CLASSES)

    def test_trade_class_is_added_when_search_misses_it(self, corpus):
        """Поиск по названию товара класс 35 не находит: в его описании
        нет ни «одежды», ни «игрушек»."""
        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        found = analyzer._retriever.retrieve("игрушки", top_k=2)
        assert all("Класс 35" not in item.chunk.anchor for item in found)

        enriched = analyzer._with_trade_services(found)
        assert any("Класс 35" in item.chunk.anchor for item in enriched)

    def test_trade_class_is_not_duplicated(self, corpus):
        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        found = analyzer._retriever.retrieve("реклама торговля", top_k=3)
        enriched = analyzer._with_trade_services(found)

        anchors = [item.chunk.anchor for item in enriched]
        assert sum("Класс 35" in anchor for anchor in anchors) == 1

    def test_added_chunk_can_be_cited(self, corpus):
        """Добавленный раздел должен попасть в контекст как источник."""
        from app.infrastructure.rag.retriever import build_context

        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        enriched = analyzer._with_trade_services(
            analyzer._retriever.retrieve("игрушки", top_k=2)
        )
        context, sources = build_context(enriched)

        assert "Класс 35" in context
        assert any("розничной" in text for text in sources.values())


class TestPromptAsksForCompleteness:
    def test_prompt_prefers_more_classes(self):
        assert "лишний раз" in SYSTEM_PROMPT
        assert "пошлину" in SYSTEM_PROMPT or "пошлин" in SYSTEM_PROMPT

    def test_prompt_mentions_online_trade(self):
        assert "интернет" in SYSTEM_PROMPT.lower()

    def test_prompt_asks_to_mark_uncertain(self):
        assert "borderline" in SYSTEM_PROMPT
