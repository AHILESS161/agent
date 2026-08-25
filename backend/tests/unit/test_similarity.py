"""Тесты оценки сходства до степени смешения.

Критерии — пункт 42 Правил № 482 (звуковое, графическое, смысловое
сходство) и пункт 162 постановления Пленума ВС РФ № 10 (вероятность
смешения через сходство обозначений и однородность товаров).

Расчёт детерминированный, поэтому поведение можно закрепить тестами.
"""

from __future__ import annotations

import pytest

from app.document_processing.similarity import (
    assess,
    goods_similarity,
    phonetic_similarity,
    semantic_similarity,
    visual_similarity,
    with_image_visual,
)


class TestPhonetic:
    def test_yo_and_ye_sound_the_same(self):
        assert phonetic_similarity("ЗВЁЗДОЧКА", "ЗВЕЗДОЧКА") == 1.0

    def test_transliteration_is_recognised(self):
        """«ЗВЕЗДА» и «ZVEZDA» звучат одинаково."""
        assert phonetic_similarity("ЗВЕЗДА", "ZVEZDA") >= 0.9

    def test_soft_sign_does_not_change_sound(self):
        assert phonetic_similarity("АЛЬФА", "АЛФА") == 1.0

    def test_doubled_consonants_are_folded(self):
        assert phonetic_similarity("АЛЛА", "АЛА") == 1.0

    def test_different_words_are_not_similar(self):
        assert phonetic_similarity("ЗВЕЗДА", "КОМЕТА") < 0.4


class TestVisual:
    def test_identical_spelling(self):
        assert visual_similarity("РОМАШКА", "РОМАШКА") == 1.0

    def test_homoglyphs_are_recognised(self):
        """Кириллическая «А» и латинская «A» неразличимы визуально."""
        assert visual_similarity("СОРТ", "COPT") >= 0.9

    def test_single_typo_stays_highly_similar(self):
        assert visual_similarity("РОМАШКА", "РАМАШКА") >= 0.8


class TestSemantic:
    def test_shared_word_gives_similarity(self):
        assert semantic_similarity("ЗОЛОТАЯ РЫБКА", "ЗОЛОТАЯ ПТИЦА") > 0.0

    def test_containment_is_detected(self):
        """Вхождение одного обозначения в другое — признак по п.42."""
        assert semantic_similarity("СБЕР", "СБЕРБАНК") >= 0.5

    def test_unrelated_words(self):
        assert semantic_similarity("ЗВЕЗДА", "МОЛОТОК") == 0.0


class TestGoodsHomogeneity:
    def test_same_class_is_homogeneous(self):
        assert goods_similarity([25], [25]) >= 0.9

    def test_overlapping_classes(self):
        assert goods_similarity([25, 35], [25]) >= 0.6

    def test_goods_versus_services_are_less_homogeneous(self):
        """Класс 25 (товары) и класс 42 (услуги) — разные группы."""
        assert goods_similarity([25], [42]) < 0.4

    def test_unknown_classes_give_neutral_value(self):
        value = goods_similarity(None, None)
        assert 0.0 < value < 0.6


class TestConfusionAssessment:
    def test_identical_mark_same_class_is_critical(self):
        result = assess("СБЕР", "СБЕР", [36], [36])
        assert result.confusion_likely is True
        assert result.level.value in ("high", "identical")

    def test_identical_mark_different_class_still_flags_risk(self):
        """По п.162 смешение возможно и при низкой однородности,
        если обозначения тождественны."""
        result = assess("ЗВЕЗДА", "ЗВЕЗДА", [30], [42])
        assert result.confusion_likely is True
        assert result.goods < 0.4

    def test_different_marks_same_class_no_confusion(self):
        result = assess("ЗВЕЗДА", "КОМЕТА", [30], [30])
        assert result.confusion_likely is False

    def test_low_similarity_but_identical_goods_can_confuse(self):
        """Обратное правило п.162: идентичность товаров усиливает риск."""
        result = assess("СБЕР", "СБЕРБАНК", [36], [36])
        assert result.goods >= 0.6
        assert result.overall > 0.5

    def test_reasons_are_explained(self):
        result = assess("АЛЬФА", "АЛФА", [36], [36])
        assert result.reasons
        assert any("звуковое" in reason for reason in result.reasons)

    def test_mark_similarity_takes_strongest_criterion(self):
        """Достаточно совпадения по одному признаку из трёх."""
        result = assess("ЗВЕЗДА", "ZVEZDA", [25], [25])
        assert result.phonetic > result.visual
        assert result.mark_similarity == pytest.approx(result.phonetic)

    def test_assessment_serialises_all_criteria(self):
        payload = assess("СБЕР", "СБЕР", [36], [36]).as_dict()
        for key in ("phonetic", "visual", "semantic", "goods", "overall", "level"):
            assert key in payload

    def test_rough_image_score_does_not_create_legal_risk(self):
        base = assess("ДРУЖЕЛЮБНЫЙ СОСЕД", "ТЕХНОЛОГИИ ПОБЕД", [37], [37])
        enriched = with_image_visual(base, 0.95)

        assert enriched.image_visual == pytest.approx(0.95)
        assert enriched.overall == pytest.approx(base.overall)
        assert enriched.mark_similarity == pytest.approx(base.mark_similarity)
        assert enriched.confusion_likely is base.confusion_likely
