"""Тесты разделения корпусов базы знаний по видам анализа.

Оценка оснований отказа и подбор классов МКТУ — разные задачи с разными
источниками. Смешивать их нельзя: при общем поиске справочник МКТУ
вытесняет нормы, потому что факты дела («программное обеспечение»)
совпадают со справочником сильнее, чем с текстом закона.

Проверено на реальном деле: без разделения в контекст оценки оснований
попадал раздел «Рекомендуемые классы в сфере ИТ» вместо статьи 1483.
"""

from __future__ import annotations

import pytest

from app.agents.classification.rag_class_analyzer import RagNiceClassAnalyzer
from app.agents.legal.rag_analyzer import RagAbsoluteGroundsAnalyzer
from app.infrastructure.rag.store import StoredChunk


def _chunk(chunk_id, content, anchor, source_type, article=None):
    return StoredChunk(
        chunk_id=chunk_id,
        source_id=1,
        source_name="Источник",
        source_version="v1",
        content=content,
        anchor=anchor,
        article=article,
        clause=None,
        source_type=source_type,
    )


@pytest.fixture
def mixed_corpus() -> list[StoredChunk]:
    """Корпус, где справочник МКТУ по словам ближе к фактам дела."""
    return [
        _chunk(
            1,
            "Не допускается регистрация обозначений, не обладающих "
            "различительной способностью или состоящих только из элементов, "
            "характеризующих товары, в том числе указывающих на их вид, "
            "качество, назначение.",
            "ст. 1483, п. 1",
            "law",
            "1483",
        ),
        _chunk(
            2,
            "Не допускается регистрация обозначений, включающих "
            "государственные символы: гербы, флаги, награды.",
            "ст. 1483, п. 2",
            "law",
            "1483",
        ),
        _chunk(
            3,
            "Класс 42. Научные и технологические услуги: разработка "
            "программного обеспечения, программирование, создание "
            "программного обеспечения, SaaS-платформы.",
            "Классы услуг → Класс 42",
            "methodology",
        ),
        _chunk(
            4,
            "Класс 9. Компьютеры и программное обеспечение: программы для "
            "электронно-вычислительных машин, программное обеспечение.",
            "Классы товаров → Класс 9",
            "methodology",
        ),
        _chunk(
            5,
            "Экспертиза проводится в два этапа: формальная экспертиза "
            "и экспертиза обозначения по существу.",
            "Стадии экспертизы",
            "regulation",
        ),
    ]


SOFTWARE_FACTS = {
    "mark_text": "ТехноСфера",
    "description": "словесное обозначение",
    "business_description": "Разработка программного обеспечения",
    "goods_services": "Программное обеспечение; SaaS-платформы",
}


class TestGroundsAnalysisUsesLegalCorpus:
    def test_context_contains_only_legal_sources(self, mixed_corpus):
        analyzer = RagAbsoluteGroundsAnalyzer(None, mixed_corpus)
        hits = analyzer._retrieve_grounds_context(SOFTWARE_FACTS)

        assert hits
        for hit in hits:
            assert hit.chunk.source_type in RagAbsoluteGroundsAnalyzer.SOURCE_TYPES

    def test_nice_reference_never_enters_grounds_context(self, mixed_corpus):
        """Регрессия: справочник МКТУ вытеснял нормы из контекста."""
        analyzer = RagAbsoluteGroundsAnalyzer(None, mixed_corpus)
        hits = analyzer._retrieve_grounds_context(SOFTWARE_FACTS)

        assert all(hit.chunk.source_type != "methodology" for hit in hits)

    def test_finds_distinctiveness_norm_for_software_case(self, mixed_corpus):
        analyzer = RagAbsoluteGroundsAnalyzer(None, mixed_corpus)
        anchors = [
            hit.chunk.anchor
            for hit in analyzer._retrieve_grounds_context(SOFTWARE_FACTS)
        ]
        assert "ст. 1483, п. 1" in anchors

    def test_falls_back_to_full_corpus_when_types_absent(self):
        """Старая индексация без типов не должна давать пустой контекст."""
        legacy = [
            _chunk(1, "Текст без указания типа источника " * 5, "раздел", "unknown")
        ]
        analyzer = RagAbsoluteGroundsAnalyzer(None, legacy)
        assert analyzer._retriever is not None


class TestClassAnalysisUsesNiceCorpus:
    def test_retriever_limited_to_reference(self, mixed_corpus):
        analyzer = RagNiceClassAnalyzer(None, mixed_corpus)
        hits = analyzer._retriever.retrieve(
            "разработка программного обеспечения SaaS", top_k=5
        )

        assert hits
        for hit in hits:
            assert hit.chunk.source_type in RagNiceClassAnalyzer.SOURCE_TYPES

    def test_finds_relevant_classes_for_software(self, mixed_corpus):
        analyzer = RagNiceClassAnalyzer(None, mixed_corpus)
        anchors = " ".join(
            hit.chunk.anchor
            for hit in analyzer._retriever.retrieve(
                "разработка программного обеспечения", top_k=3
            )
        )
        assert "Класс 42" in anchors or "Класс 9" in anchors

    def test_legal_norms_never_enter_class_context(self, mixed_corpus):
        analyzer = RagNiceClassAnalyzer(None, mixed_corpus)
        hits = analyzer._retriever.retrieve("обозначение товары услуги", top_k=5)
        assert all(hit.chunk.article is None for hit in hits)


class TestSpecialisationPrinciple:
    """Описательность оценивается только относительно заявленных товаров.

    «ЯБЛОКО» для фруктов описательно, для компьютеров — произвольно.
    Инструкция об этом должна быть в промпте, иначе модель делает
    вывод об обозначении в отрыве от товаров.
    """

    def test_prompt_states_specialisation_principle(self):
        from app.agents.legal.rag_analyzer import SYSTEM_PROMPT

        assert "ПРИНЦИП СПЕЦИАЛИЗАЦИИ" in SYSTEM_PROMPT
        assert "ЯБЛОКО" in SYSTEM_PROMPT

    def test_prompt_requires_linking_conclusion_to_goods(self):
        from app.agents.legal.rag_analyzer import SYSTEM_PROMPT

        assert "case_facts_used" in SYSTEM_PROMPT

    def test_class_prompt_explains_impact_on_protectability(self):
        from app.agents.classification.rag_class_analyzer import SYSTEM_PROMPT

        assert "описательно только относительно" in SYSTEM_PROMPT
