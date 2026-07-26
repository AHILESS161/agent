"""Тесты смыслового сходства обозначений.

Главное, что здесь проверяется, — дисциплина обращения к модели:
её спрашивают только там, где ответ меняет вывод, и её ответ никогда
не ослабляет оценку, полученную по правилам.
"""

from __future__ import annotations

import json

import pytest

from app.agents.legal.semantic_similarity import (
    SemanticRelation,
    SemanticSimilarityAnalyzer,
    describe,
    needs_semantic_check,
)
from app.document_processing.similarity import assess, with_semantic


class StubLLM:
    """Модель, отвечающая заранее заданным текстом."""

    MODEL_NAME = "stub"

    def __init__(self, response: str | None):
        self._response = response
        self.calls: list[str] = []

    async def generate(self, messages, temperature=0.1, max_tokens=4096):
        self.calls.append(" ".join(m.content for m in messages))
        if self._response is None:
            raise RuntimeError("модель недоступна")

        class _R:
            content = self._response

        return _R()


def _verdict_json(relation: str, **extra) -> str:
    payload = {
        "relation": relation,
        "left_meaning": "плод яблони",
        "right_meaning": "the fruit of the apple tree",
        "rationale": "Оба обозначения означают яблоко.",
    }
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


class TestWhenModelIsAsked:
    """Вызов модели должен быть оправдан: он стоит денег и времени."""

    def test_skipped_when_marks_already_similar(self):
        """Звуковое сходство уже установлено — смысл ничего не добавит."""
        similarity = assess("ЗВЕЗДА", "ZVEZDA", [25], [25])
        assert similarity.mark_similarity >= 0.75
        assert needs_semantic_check(similarity, "ЗВЕЗДА", "ZVEZDA") is False

    def test_skipped_when_goods_are_not_homogeneous(self):
        """Без однородности товаров смешения не будет даже при совпадении."""
        similarity = assess("ЯБЛОКО", "APPLE", [25], [1])
        assert similarity.goods < 0.4
        assert needs_semantic_check(similarity, "ЯБЛОКО", "APPLE") is False

    def test_requested_for_cross_language_pair(self):
        """Тот самый случай, ради которого нужна модель."""
        similarity = assess("ЯБЛОКО", "APPLE", [25], [25])
        assert similarity.semantic == 0.0
        assert needs_semantic_check(similarity, "ЯБЛОКО", "APPLE") is True

    def test_requested_when_classes_are_unknown(self):
        """Неизвестные классы — не повод пропустить смысловое совпадение."""
        similarity = assess("ЯБЛОКО", "APPLE", None, None)
        assert similarity.goods < 0.4

        assert needs_semantic_check(similarity, "ЯБЛОКО", "APPLE") is False
        assert (
            needs_semantic_check(similarity, "ЯБЛОКО", "APPLE", goods_known=False)
            is True
        )

    @pytest.mark.parametrize("mark", ["", " ", "5", "!"])
    def test_skipped_for_non_verbal_marks(self, mark):
        similarity = assess("ЯБЛОКО", mark, [25], [25])
        assert needs_semantic_check(similarity, "ЯБЛОКО", mark) is False


class TestVerdictParsing:
    async def test_translation_is_recognised(self):
        analyzer = SemanticSimilarityAnalyzer(StubLLM(_verdict_json("translation")))
        verdict = await analyzer.analyze("ЯБЛОКО", "APPLE")

        assert verdict.relation is SemanticRelation.translation
        assert verdict.score >= 0.9
        assert verdict.llm_used is True
        assert verdict.model_name == "stub"

    async def test_unknown_relation_is_rejected(self):
        """Вид связи вне закрытого списка доверия не заслуживает."""
        analyzer = SemanticSimilarityAnalyzer(
            StubLLM(_verdict_json("очень_похоже"))
        )
        verdict = await analyzer.analyze("ЯБЛОКО", "APPLE")

        assert verdict.relation is SemanticRelation.unrelated
        assert verdict.score == 0.0
        assert verdict.is_meaningful is False

    async def test_broken_answer_gives_no_relation(self):
        analyzer = SemanticSimilarityAnalyzer(StubLLM("я не понял вопрос"))
        verdict = await analyzer.analyze("ЯБЛОКО", "APPLE")
        assert verdict.relation is SemanticRelation.unrelated

    async def test_model_failure_gives_no_relation(self):
        """Отказ модели не должен ронять анализ."""
        analyzer = SemanticSimilarityAnalyzer(StubLLM(None))
        verdict = await analyzer.analyze("ЯБЛОКО", "APPLE")

        assert verdict.relation is SemanticRelation.unrelated
        assert verdict.llm_used is False

    async def test_answer_is_wrapped_in_markdown(self):
        """Слабые модели любят markdown-обёртку."""
        raw = "```json\n" + _verdict_json("same_concept") + "\n```"
        analyzer = SemanticSimilarityAnalyzer(StubLLM(raw))
        verdict = await analyzer.analyze("МОРЖ", "ПОЛЯРНЫЙ ЗВЕРЬ")
        assert verdict.relation is SemanticRelation.same_concept

    async def test_marks_are_passed_to_the_model(self):
        llm = StubLLM(_verdict_json("translation"))
        await SemanticSimilarityAnalyzer(llm).analyze("ЯБЛОКО", "APPLE")

        assert "ЯБЛОКО" in llm.calls[0]
        assert "APPLE" in llm.calls[0]


class TestScoreCannotBeLowered:
    """Ответ модели только повышает смысловую оценку."""

    def test_lower_score_is_ignored(self):
        base = assess("СВЕЖИЙ ХЛЕБ", "СВЕЖИЙ ХЛЕБ", [30], [30])
        assert base.semantic == 1.0

        updated = with_semantic(base, 0.45)
        assert updated.semantic == 1.0
        assert updated.semantic_source == "rules"

    def test_higher_score_changes_conclusion(self):
        base = assess("ЯБЛОКО", "APPLE", [25], [25])
        assert base.confusion_likely is False

        updated = with_semantic(base, 0.9)
        assert updated.semantic == 0.9
        assert updated.semantic_source == "llm"
        assert updated.confusion_likely is True

    def test_deterministic_criteria_are_untouched(self):
        """Модель отвечает за смысл и только за него."""
        base = assess("ЯБЛОКО", "APPLE", [25], [25])
        updated = with_semantic(base, 0.9)

        assert updated.phonetic == base.phonetic
        assert updated.visual == base.visual
        assert updated.goods == base.goods

    def test_source_is_visible_in_output(self):
        updated = with_semantic(assess("ЯБЛОКО", "APPLE", [25], [25]), 0.9)
        data = updated.as_dict()

        assert data["semantic_source"] == "llm"
        assert any("языковой модел" in reason for reason in data["reasons"])


class TestExplanation:
    def test_meaningful_verdict_is_explained(self):
        analyzer_output = SemanticRelation.translation
        from app.agents.legal.semantic_similarity import SemanticVerdict

        text = describe(
            SemanticVerdict(
                relation=analyzer_output,
                score=0.9,
                rationale="Оба обозначения означают яблоко.",
                left_meaning="плод яблони",
                right_meaning="the fruit of the apple tree",
                llm_used=True,
            ),
            "ЯБЛОКО",
            "APPLE",
        )

        assert "прямой перевод" in text
        assert "плод яблони" in text
        # Специалист обязан видеть, что вывод сделан моделью.
        assert "языковой моделью" in text

    def test_no_relation_gives_no_text(self):
        from app.agents.legal.semantic_similarity import unrelated_verdict

        assert describe(unrelated_verdict("нет связи"), "A", "B") == ""
