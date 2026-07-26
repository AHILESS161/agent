"""Тесты связки «классы МКТУ → оценка оснований отказа».

Различительная способность оценивается только применительно
к конкретным товарам: «ЯБЛОКО» для свежих фруктов описательно,
для компьютеров — произвольно. Поэтому перечень классов входит
в исходные данные вывода, а его неподтверждённость должна быть
видна в ограничениях анализа.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import NiceClassSuggestion
from app.services.class_analysis import ClassContext


def _suggestion(number: int, description: str, approved: bool | None) -> NiceClassSuggestion:
    return NiceClassSuggestion(
        application_id=1,
        class_number=number,
        class_description=description,
        approved=approved,
    )


class TestClassContext:
    def test_approved_classes_take_priority(self):
        context = ClassContext(
            approved=[_suggestion(25, "одежда", True)],
            suggested=[_suggestion(9, "программы", None)],
        )
        assert context.as_numbers() == [25]
        assert context.is_confirmed is True

    def test_falls_back_to_suggested_when_nothing_approved(self):
        context = ClassContext(
            approved=[], suggested=[_suggestion(9, "программы", None)]
        )
        assert context.as_numbers() == [9]
        assert context.is_confirmed is False
        assert context.has_any is True

    def test_empty_context_reports_absence(self):
        context = ClassContext(approved=[], suggested=[])
        assert context.has_any is False
        assert context.describe() == "не определены"

    def test_description_includes_goods_for_each_class(self):
        """Модель должна видеть не только номер, но и товары класса."""
        context = ClassContext(
            approved=[_suggestion(25, "одежда, обувь", True)], suggested=[]
        )
        described = context.describe()
        assert "25" in described
        assert "одежда" in described


class TestSpecialisationDependsOnClasses:
    """Один и тот же знак оценивается по-разному для разных классов."""

    def test_same_mark_different_classes_gives_different_context(self):
        fruits = ClassContext(approved=[_suggestion(31, "свежие фрукты", True)], suggested=[])
        computers = ClassContext(approved=[_suggestion(9, "компьютеры", True)], suggested=[])

        assert fruits.describe() != computers.describe()
        assert fruits.as_numbers() != computers.as_numbers()


@pytest.mark.parametrize(
    ("approved", "suggested", "expect_confirmed"),
    [
        ([25], [], True),
        ([], [25], False),
        ([], [], False),
    ],
)
def test_confirmation_flag(approved, suggested, expect_confirmed):
    context = ClassContext(
        approved=[_suggestion(n, "", True) for n in approved],
        suggested=[_suggestion(n, "", None) for n in suggested],
    )
    assert context.is_confirmed is expect_confirmed


class TestChunkerRegression:
    """Регрессии, найденные на реальном справочнике МКТУ."""

    def test_short_sections_are_not_dropped(self):
        """«Класс 25. Одежда и обувь» — 30 символов.

        При пороге в 120 символов раздел выпадал из индекса, и запрос
        «производство одежды» не находил его вовсе.
        """
        from app.infrastructure.rag.chunker import chunk_markdown

        text = "## Классы\n\n### Класс 25. Одежда и обувь\n\nОдежда, обувь, головные уборы.\n"
        chunks = chunk_markdown(text)

        assert any("Класс 25" in c.content for c in chunks)

    def test_heading_is_included_in_indexed_content(self):
        """Заголовок несёт самую плотную информацию и обязан искаться."""
        from app.infrastructure.rag.chunker import chunk_markdown

        text = "### Класс 43. Услуги в области питания\n\nРестораны, кафе, гостиницы.\n"
        chunks = chunk_markdown(text)

        assert chunks
        assert "Класс 43" in chunks[0].content
        assert "питания" in chunks[0].content
