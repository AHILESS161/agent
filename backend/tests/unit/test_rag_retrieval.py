"""Тесты стемминга и поиска по базе знаний.

Без стемминга поиск по русскому тексту не работает: в норме написано
«гербами, флагами», а специалист ищет «герб, флаг». Проверено на
реальной базе знаний проекта — запрос про государственную символику
не поднимал пункт 4 статьи 1483, где она как раз и описана.
"""

from __future__ import annotations

import pytest

from app.infrastructure.rag.retriever import Retriever, build_context
from app.infrastructure.rag.stemmer import stem
from app.infrastructure.rag.store import StoredChunk


class TestStemmer:
    @pytest.mark.parametrize(
        "forms",
        [
            ["герб", "гербами", "гербов", "гербу"],
            ["флаг", "флаги", "флагами", "флагов"],
            ["товар", "товары", "товаров", "товарами"],
            ["знак", "знака", "знаков", "знаками"],
            ["обозначение", "обозначения", "обозначений", "обозначением"],
            ["регистрация", "регистрации", "регистрацию"],
            ["различительный", "различительная", "различительной"],
            ["смешение", "смешения", "смешению"],
            ["государственный", "государственная", "государственными"],
        ],
    )
    def test_word_forms_share_one_stem(self, forms):
        stems = {stem(form) for form in forms}
        assert len(stems) == 1, f"{forms} → {stems}"

    def test_genitive_plural_is_not_confused_with_gerund(self):
        """Регрессия: «гербов» превращалось в «гербо».

        Окончание деепричастия «в» отсекается только после «а» или «я»,
        иначе оно съедает родительный падеж множественного числа.
        """
        assert stem("гербов") == stem("герб")
        assert stem("товаров") == stem("товар")

    def test_short_words_are_left_alone(self):
        assert stem("иск") == "иск"

    def test_yo_is_normalised(self):
        assert stem("учёт") == stem("учет")

    def test_latin_and_digits_pass_through(self):
        assert stem("mktu") == "mktu"
        assert stem("1483") == "1483"

    def test_different_words_keep_different_stems(self):
        """Стемминг не должен склеивать несвязанные слова."""
        assert stem("товар") != stem("товарищ")


def _chunk(chunk_id: int, content: str, anchor: str, article: str | None = None) -> StoredChunk:
    return StoredChunk(
        chunk_id=chunk_id,
        source_id=1,
        source_name="ГК РФ Часть IV",
        source_version="v1",
        content=content,
        anchor=anchor,
        article=article,
        clause=None,
    )


@pytest.fixture
def chunks() -> list[StoredChunk]:
    return [
        _chunk(
            1,
            "Не допускается регистрация обозначений, не обладающих "
            "различительной способностью или состоящих только из элементов, "
            "характеризующих товары.",
            "ст. 1483, п. 1",
            "1483",
        ),
        _chunk(
            2,
            "Не могут быть зарегистрированы обозначения, тождественные или "
            "сходные до степени смешения с государственными символами: "
            "гербами, флагами, официальными наименованиями государств.",
            "ст. 1483, п. 4",
            "1483",
        ),
        _chunk(
            3,
            "Не могут быть зарегистрированы обозначения, сходные до степени "
            "смешения с товарными знаками других лиц, охраняемыми в Российской "
            "Федерации в отношении однородных товаров.",
            "ст. 1483, п. 6",
            "1483",
        ),
        _chunk(
            4,
            "Международная классификация товаров и услуг содержит 45 классов: "
            "с 1 по 34 — товары, с 35 по 45 — услуги.",
            "МКТУ",
            None,
        ),
    ]


class TestRetrieval:
    def test_finds_norm_despite_different_word_forms(self, chunks):
        """Ключевая проверка: «герб, флаг» находит «гербами, флагами»."""
        hits = Retriever(chunks).retrieve("государственная символика герб флаг")
        assert hits
        assert hits[0].chunk.anchor == "ст. 1483, п. 4"

    def test_finds_distinctiveness_norm(self, chunks):
        hits = Retriever(chunks).retrieve(
            "обозначение не обладает различительной способностью"
        )
        assert hits[0].chunk.anchor == "ст. 1483, п. 1"

    def test_finds_confusion_norm(self, chunks):
        hits = Retriever(chunks).retrieve("сходство до степени смешения с чужим знаком")
        assert hits[0].chunk.anchor == "ст. 1483, п. 6"

    def test_irrelevant_query_returns_nothing(self, chunks):
        assert Retriever(chunks).retrieve("рецепт борща на говяжьем бульоне") == []

    def test_empty_query_returns_nothing(self, chunks):
        assert Retriever(chunks).retrieve("") == []

    def test_empty_knowledge_base_returns_nothing(self):
        assert Retriever([]).retrieve("любой запрос") == []

    def test_article_filter_narrows_search(self, chunks):
        hits = Retriever(chunks).retrieve("товары классы", article="1483")
        assert all(hit.chunk.article == "1483" for hit in hits)

    def test_top_k_is_respected(self, chunks):
        assert len(Retriever(chunks).retrieve("товары знаки обозначения", top_k=2)) <= 2


class TestContextBuilding:
    def test_context_contains_source_ids_for_verification(self, chunks):
        hits = Retriever(chunks).retrieve("различительная способность")
        context, sources = build_context(hits)

        assert "source_id:" in context
        # Карта источников нужна для последующей проверки цитат.
        for hit in hits:
            assert hit.citation_id in sources
            assert sources[hit.citation_id] == hit.chunk.content

    def test_context_includes_anchor_for_the_specialist(self, chunks):
        hits = Retriever(chunks).retrieve("государственные символы герб")
        context, _ = build_context(hits)
        assert "ст. 1483" in context

    def test_empty_retrieval_yields_empty_context(self):
        context, sources = build_context([])
        assert context == ""
        assert sources == {}
