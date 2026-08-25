"""Точность подбора классов МКТУ и явное основание для класса 35."""

from __future__ import annotations

import pytest

from app.agents.classification.rag_class_analyzer import (
    ALWAYS_INCLUDE_CLASSES,
    RagNiceClassAnalyzer,
    SYSTEM_PROMPT,
)
from app.infrastructure.rag.store import StoredChunk
from app.services.class_analysis import _apply_service_intent, _service_intent
from app.agents.classification.rag_class_analyzer import ClassSuggestion


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


class TestTradeServicesRequireExplicitActivity:
    """Класс 35 нужен при явно заявленной торговле, но не производству вообще."""

    def test_trade_class_is_declared(self):
        assert any("35" in marker for marker in ALWAYS_INCLUDE_CLASSES)

    def test_trade_class_is_not_added_for_product_only(self, corpus):
        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        found = analyzer._retriever.retrieve("игрушки", top_k=2)
        enriched = analyzer._with_trade_services(found, "производство игрушек")

        assert all("Класс 35" not in item.chunk.anchor for item in enriched)

    def test_trade_class_is_added_for_explicit_sales(self, corpus):
        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        found = analyzer._retriever.retrieve("игрушки", top_k=2)
        enriched = analyzer._with_trade_services(found, "продажа игрушек")

        assert any("Класс 35" in item.chunk.anchor for item in enriched)

    def test_trade_class_is_not_duplicated(self, corpus):
        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        found = analyzer._retriever.retrieve("реклама торговля", top_k=3)
        enriched = analyzer._with_trade_services(found, "реклама и торговля")

        anchors = [item.chunk.anchor for item in enriched]
        assert sum("Класс 35" in anchor for anchor in anchors) == 1

    def test_added_chunk_can_be_cited(self, corpus):
        """Добавленный раздел должен попасть в контекст как источник."""
        from app.infrastructure.rag.retriever import build_context

        analyzer = RagNiceClassAnalyzer(llm_provider=None, chunks=corpus)
        enriched = analyzer._with_trade_services(
            analyzer._retriever.retrieve("игрушки", top_k=2),
            "продажа игрушек через интернет-магазин",
        )
        context, sources = build_context(enriched)

        assert "Класс 35" in context
        assert any("розничной" in text for text in sources.values())


class TestPromptAsksForPrecision:
    def test_prompt_rejects_speculative_classes(self):
        assert "только классы" in SYSTEM_PROMPT
        assert "на всякий случай" in SYSTEM_PROMPT

    def test_prompt_mentions_online_trade(self):
        assert "интернет" in SYSTEM_PROMPT.lower()

    def test_prompt_asks_to_mark_uncertain(self):
        assert "borderline" in SYSTEM_PROMPT


class TestServiceIntentCorrection:
    def test_phone_and_computer_repair_is_class_37(self):
        required, service_only = _service_intent(
            "Ремонтирую телефоны и компьютеры"
        )

        assert required == {37}
        assert service_only is True

    def test_repair_does_not_claim_the_devices_as_goods(self):
        wrong_product = ClassSuggestion(
            class_number=9,
            rationale="Телефоны и компьютеры являются устройствами класса 9.",
            goods_services=["телефоны", "компьютеры"],
            confidence=0.7,
        )

        corrected = _apply_service_intent(
            [wrong_product],
            "Ремонтирую телефоны и компьютеры",
        )

        assert [item.class_number for item in corrected] == [37]

    def test_sales_and_repair_keep_goods_and_service_classes(self):
        product = ClassSuggestion(
            class_number=9,
            rationale="Продажа телефонов и компьютеров относится к устройствам.",
            goods_services=["телефоны", "компьютеры"],
            confidence=0.8,
        )

        corrected = _apply_service_intent(
            [product],
            "Продаю и ремонтирую телефоны и компьютеры",
        )

        assert {item.class_number for item in corrected} == {9, 37}
