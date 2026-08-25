"""Синхронизатор МКТУ принимает только полный и узнаваемый ответ ФИПС."""

from __future__ import annotations

import pytest

from scripts.sync_nice_classification import NiceClassPage, parse_class_page, render_markdown


def test_parse_fips_class_page() -> None:
    document = """
    <div class="boldtext"><b>Одежда, обувь, головные уборы.</b></div>
    <div class="oneline name">одежда для автомобилистов</div>
    <div class="oneline"><div>250002</div><div>E — motorists' clothing</div></div>
    <div class="oneline name">обувь*</div>
    <div class="oneline"><div>250003</div><div>E — footwear*</div></div>
    """

    result = parse_class_page(25, document)

    assert result.number == 25
    assert result.title == "Одежда, обувь, головные уборы."
    assert result.items == (
        ("250002", "одежда для автомобилистов"),
        ("250003", "обувь*"),
    )


def test_parser_rejects_page_without_items() -> None:
    with pytest.raises(ValueError, match="перечень позиций"):
        parse_class_page(25, '<div class="boldtext"><b>Одежда</b></div>')


def test_renderer_rejects_incomplete_snapshot() -> None:
    with pytest.raises(ValueError, match="все 45 классов"):
        render_markdown(
            [NiceClassPage(number=25, title="Одежда", items=(("250003", "обувь"),))],
            "2026-08-19",
        )
