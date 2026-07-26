"""Демонстрационный реестр: поиск не должен молча возвращать пустоту.

Вид знака в наборе данных записан по-русски, а система оперирует
значениями перечисления MarkType. Пока эти словари не были сведены,
фильтр отбрасывал каждую запись, и поиск конфликтов возвращал «ничего
не найдено» — вывод, неотличимый от честного отсутствия конфликтов.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import MarkType
from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.providers.mock_fips import MockFipsProvider


@pytest.fixture
def provider() -> MockFipsProvider:
    return MockFipsProvider()


class TestMarkTypeFilter:
    async def test_word_mark_query_finds_word_marks(self, provider):
        results = await provider.search_marks(
            SearchQuery(
                mark_text="СБЕРБАНК",
                mark_type=MarkType.word.value,
                search_type="exact",
            )
        )
        assert [r.mark_text for r in results] == ["СБЕРБАНК"]

    async def test_query_without_mark_type_still_works(self, provider):
        results = await provider.search_marks(
            SearchQuery(mark_text="СБЕРБАНК", search_type="exact")
        )
        assert results

    async def test_mismatched_mark_type_filters_out(self, provider):
        """Фильтр обязан работать, а не пропускать всё подряд."""
        results = await provider.search_marks(
            SearchQuery(
                mark_text="СБЕРБАНК",
                mark_type=MarkType.sound.value,
                search_type="exact",
            )
        )
        assert results == []


class TestFuzzySearch:
    async def test_similar_mark_is_found(self, provider):
        results = await provider.search_marks(
            SearchQuery(
                mark_text="СБЕРБАНКЪ",
                mark_type=MarkType.word.value,
                search_type="fuzzy",
            )
        )
        assert any(r.mark_text == "СБЕРБАНК" for r in results)
