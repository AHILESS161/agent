"""Варианты поискового запроса к реестру.

Реестр ищет по написанию, поэтому переводной знак нужно сначала найти.
Проверяется, что варианты действительно расширяют запрос и что текст,
уходящий во внешнюю систему, остаётся под контролем: всё, что вернула
модель, проходит проверку формы.
"""

from __future__ import annotations

import json

import pytest

from app.agents.legal.query_variants import (
    MAX_VARIANT_CHARS,
    QueryVariantGenerator,
    deterministic_variants,
)


class StubLLM:
    MODEL_NAME = "stub"

    def __init__(self, payload):
        self._payload = payload

    async def generate(self, messages, temperature=0.1, max_tokens=4096):
        class _R:
            content = (
                self._payload
                if isinstance(self._payload, str)
                else json.dumps(self._payload, ensure_ascii=False)
            )

        return _R()


class TestDeterministicVariants:
    def test_original_is_always_present(self):
        variants = deterministic_variants("ЯБЛОКО")
        assert variants[0].text == "ЯБЛОКО"
        assert variants[0].kind == "original"

    def test_cyrillic_mark_gets_transliteration(self):
        kinds = {v.kind: v.text for v in deterministic_variants("ЗВЕЗДА")}
        assert kinds["transliteration"] == "ZVEZDA"

    def test_latin_mark_is_not_transliterated(self):
        """Для латиницы транслитерация ничего не добавляет."""
        variants = deterministic_variants("APPLE")
        assert [v.kind for v in variants] == ["original"]

    def test_transliteration_needs_no_model(self):
        assert all(not v.llm_used for v in deterministic_variants("ЗВЕЗДА"))


class TestTranslationVariants:
    async def test_translation_is_added(self):
        generator = QueryVariantGenerator(
            StubLLM({
                "has_meaning": True,
                "meaning": "плод яблони",
                "translations": ["apple"],
            })
        )
        variants = await generator.build("ЯБЛОКО")

        translations = [v for v in variants if v.kind == "translation"]
        assert [v.text for v in translations] == ["APPLE"]
        assert translations[0].llm_used is True

    async def test_meaningless_mark_gets_no_translation(self):
        """Выдуманное слово переводить нечего."""
        generator = QueryVariantGenerator(
            StubLLM({"has_meaning": False, "meaning": "", "translations": ["нечто"]})
        )
        variants = await generator.build("ЗЯБРИКС")

        assert [v.kind for v in variants] == ["original", "transliteration"]

    async def test_no_model_means_only_rules(self):
        variants = await QueryVariantGenerator(None).build("ЯБЛОКО")
        assert all(not v.llm_used for v in variants)

    async def test_broken_answer_is_survivable(self):
        generator = QueryVariantGenerator(StubLLM("вот что я думаю"))
        variants = await generator.build("ЯБЛОКО")
        assert [v.kind for v in variants] == ["original", "transliteration"]


class TestUntrustedTextIsFiltered:
    """Вариант уходит во внешний реестр — произвольный текст недопустим."""

    @pytest.mark.parametrize(
        "value",
        [
            "a" * (MAX_VARIANT_CHARS + 1),
            "слишком много слов в одном варианте",
            "APPLE; DROP TABLE marks",
            "перевод (фрукт)",
            "",
            "   ",
            123,
            None,
        ],
    )
    async def test_invalid_variant_is_dropped(self, value):
        generator = QueryVariantGenerator(
            StubLLM({"has_meaning": True, "meaning": "x", "translations": [value]})
        )
        variants = await generator.build("ЯБЛОКО")

        assert [v.kind for v in variants] == ["original", "transliteration"]

    async def test_valid_variant_survives_alongside_invalid(self):
        generator = QueryVariantGenerator(
            StubLLM({
                "has_meaning": True,
                "meaning": "x",
                "translations": ["a" * 80, "apple"],
            })
        )
        variants = await generator.build("ЯБЛОКО")

        assert [v.text for v in variants if v.kind == "translation"] == ["APPLE"]

    async def test_duplicate_of_original_is_not_repeated(self):
        generator = QueryVariantGenerator(
            StubLLM({
                "has_meaning": True,
                "meaning": "x",
                "translations": ["ЯБЛОКО"],
            })
        )
        variants = await generator.build("ЯБЛОКО")

        assert sum(1 for v in variants if v.text.upper() == "ЯБЛОКО") == 1
