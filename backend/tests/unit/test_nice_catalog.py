"""Справочник классов МКТУ и поиск по нему.

Класс выбирается по смыслу, а не по номеру: держать в голове все 45
классов невозможно. Перечень берётся из того же файла базы знаний,
что использует RAG, — второго списка классов в системе быть не должно.
"""

from __future__ import annotations

import pytest

from app.services.nice_catalog import load_catalog, search


class TestCatalog:
    def test_all_45_classes_are_present(self):
        catalog = load_catalog()
        assert len(catalog) == 45
        assert {item.number for item in catalog} == set(range(1, 46))

    def test_every_class_has_title_and_description(self):
        for item in load_catalog():
            assert item.title, item.number
            assert item.description, item.number

    def test_goods_and_services_are_distinguished(self):
        """Классы 1–34 — товары, 35–45 — услуги."""
        catalog = {item.number: item for item in load_catalog()}
        assert catalog[25].kind == "товары"
        assert catalog[35].kind == "услуги"

    def test_last_class_description_is_bounded(self):
        """Регрессия: описание класса 45 захватывало остаток файла,
        и класс находился по любому запросу."""
        catalog = {item.number: item for item in load_catalog()}
        assert len(catalog[45].description) < 1000


class TestSearch:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("одежда", 25),
            ("обувь", 25),
            ("кофе", 30),
            ("юридические", 45),
            ("реклама", 35),
        ],
    )
    def test_finds_class_by_word(self, query, expected):
        assert search(query, limit=3)[0].number == expected

    def test_finds_class_by_number(self):
        assert search("25")[0].number == 25

    def test_multiword_query_works(self):
        """«Разработка программ» дословно в справочнике не встречается."""
        assert search("разработка программ", limit=3)[0].number == 42

    def test_word_form_is_ignored(self):
        """Падеж не должен мешать: «одежды» — та же «одежда»."""
        assert search("производство одежды", limit=3)[0].number == 25

    def test_household_appliance_repair_prefers_repair_services(self):
        """«Бытовой» не должен уводить ремонт техники в канцтовары."""
        assert search("ремонт бытовой техники", limit=1)[0].number == 37

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("смартфоны", 9),
            ("аренда смартфонов", 38),
            ("цепочки для кошельков", 18),
        ],
    )
    def test_finds_positions_from_current_fips_snapshot(self, query, expected):
        """Конкретные позиции МКТУ 13-2026 отсутствовали в старом обзоре."""
        assert search(query, limit=3)[0].number == expected

    def test_empty_query_returns_whole_catalog(self):
        assert len(search("", limit=45)) == 45

    def test_nonsense_returns_nothing(self):
        assert search("ааабввв") == []

    def test_limit_is_respected(self):
        assert len(search("услуги", limit=2)) <= 2
