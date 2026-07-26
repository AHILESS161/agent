"""Тесты анализатора с RAG.

Ключевая проверка: вывод, не подтверждённый источниками, не попадает
к специалисту — независимо от того, насколько убедительно он выглядит.
"""

from __future__ import annotations

import json

import pytest

from app.agents.legal.rag_analyzer import RagAbsoluteGroundsAnalyzer, _parse_json
from app.infrastructure.rag.store import StoredChunk

CHUNK_TEXT = (
    "Не допускается государственная регистрация в качестве товарных знаков "
    "обозначений, не обладающих различительной способностью или состоящих "
    "только из элементов, характеризующих товары, в том числе указывающих "
    "на их вид, качество, количество, свойство, назначение, ценность."
)


@pytest.fixture
def chunks() -> list[StoredChunk]:
    return [
        StoredChunk(
            chunk_id=1,
            source_id=1,
            source_name="ГК РФ Часть IV",
            source_version="v1",
            content=CHUNK_TEXT,
            anchor="ст. 1483, п. 1",
            article="1483",
            clause="1",
        )
    ]


class FakeLLM:
    """Подставная модель с заранее заданным ответом."""

    def __init__(self, response: str | None) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, prompt: str, system: str = "", temperature: float = 0.0):
        self.calls += 1
        if self.response is None:
            raise RuntimeError("модель недоступна")
        return self.response


def _valid_response(quote: str, source_id: str = "kb-1") -> str:
    return json.dumps(
        {
            "overall_risk": "high",
            "summary": "Обозначение носит описательный характер для заявленных товаров",
            "findings": [
                {
                    "category": "descriptive",
                    "level": "high",
                    "legal_basis": "ГК РФ ст. 1483 п. 1",
                    "explanation": "Обозначение прямо указывает на вид и назначение товара",
                    "case_facts_used": ["Обозначение «СВЕЖИЙ ХЛЕБ» для класса 30"],
                    "citations": [
                        {"source_id": source_id, "quote": quote, "anchor": "ст. 1483, п. 1"}
                    ],
                    "confidence": 0.8,
                    "missing_data": [],
                    "recommended_action": "Рассмотреть добавление различительного элемента",
                }
            ],
            "limitations": ["Предварительная оценка на ограниченной базе знаний"],
            "missing_data": [],
            "requires_specialist_review": True,
        },
        ensure_ascii=False,
    )


FACTS = {
    "mark_text": "СВЕЖИЙ ХЛЕБ",
    "mark_type": "словесный",
    "description": "Словесное обозначение",
    "goods_services": "хлебобулочные изделия",
    "classes": "30",
}


class TestVerifiedFindingsSurvive:
    async def test_finding_with_real_quote_is_returned(self, chunks):
        llm = FakeLLM(_valid_response("состоящих только из элементов, характеризующих товары"))
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert outcome.is_conclusive
        assert len(outcome.result.findings) == 1
        assert outcome.result.findings[0].citations_verified is True

    async def test_verification_stats_are_reported(self, chunks):
        llm = FakeLLM(_valid_response("состоящих только из элементов, характеризующих товары"))
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert outcome.verification["citations_verified"] >= 1
        assert outcome.verification["findings_confirmed"] == 1


class TestHallucinationsAreRejected:
    """Главное свойство контура."""

    async def test_fabricated_quote_drops_the_finding(self, chunks):
        llm = FakeLLM(
            _valid_response(
                "Заявитель обязан уплатить пошлину в размере 50000 рублей "
                "и представить нотариальное согласие"
            )
        )
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert not outcome.is_conclusive
        assert outcome.insufficient is not None
        assert "Недостаточно подтверждённых данных" in outcome.insufficient.message

    async def test_reference_to_unknown_source_drops_the_finding(self, chunks):
        llm = FakeLLM(
            _valid_response(
                "состоящих только из элементов, характеризующих товары",
                source_id="kb-999",
            )
        )
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)
        assert not outcome.is_conclusive

    async def test_rejection_reason_is_recorded(self, chunks):
        llm = FakeLLM(_valid_response("Полностью выдуманная норма о размере пошлины"))
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        rejected = outcome.verification["findings_rejected"]
        assert rejected
        assert rejected[0]["reason"] == "нет подтверждённых цитат"


class TestInvalidModelOutput:
    async def test_invalid_json_yields_insufficient_data(self, chunks):
        llm = FakeLLM("Извините, я не могу выполнить этот запрос.")
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert not outcome.is_conclusive
        assert "JSON" in outcome.insufficient.reason

    async def test_schema_violation_yields_insufficient_data(self, chunks):
        """Ответ — валидный JSON, но не соответствует схеме."""
        llm = FakeLLM(json.dumps({"risk": "высокий", "текст": "всё хорошо"}, ensure_ascii=False))
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert not outcome.is_conclusive
        assert "схеме" in outcome.insufficient.reason

    async def test_llm_failure_is_handled(self, chunks):
        llm = FakeLLM(None)
        outcome = await RagAbsoluteGroundsAnalyzer(llm, chunks).analyse(FACTS)

        assert not outcome.is_conclusive
        assert outcome.insufficient is not None

    async def test_empty_knowledge_base_yields_insufficient_data(self):
        llm = FakeLLM(_valid_response("любая цитата"))
        outcome = await RagAbsoluteGroundsAnalyzer(llm, []).analyse(FACTS)

        assert not outcome.is_conclusive
        assert "базе знаний" in outcome.insufficient.reason
        # Модель не должна была вызываться вовсе.
        assert llm.calls == 0


class TestJsonExtraction:
    """Слабые модели оборачивают JSON в markdown или добавляют пояснения."""

    def test_plain_json(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_json_in_markdown_block(self):
        assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_surrounding_text(self):
        assert _parse_json('Вот результат:\n{"a": 1}\nНадеюсь, помог.') == {"a": 1}

    def test_broken_json_returns_none(self):
        assert _parse_json("это не json") is None

    def test_reasoning_with_braces_before_json(self):
        """Модели с рассуждениями пишут скобки в пояснительном тексте.

        Регрессия: разбор «от первой { до последней }» захватывал
        рассуждение вместе с ответом и падал, из-за чего анализ
        возвращал «Ответ модели не является валидным JSON».
        """
        raw = (
            "Рассуждение: схема вида {class_number, rationale} требует\n"
            "указать класс. Итог:\n"
            '```json\n{"suggestions": [{"class_number": 9}]}\n```'
        )
        assert _parse_json(raw) == {"suggestions": [{"class_number": 9}]}

    def test_fence_not_at_the_start(self):
        raw = 'Ответ ниже.\n```json\n{"a": 1}\n```\nГотово.'
        assert _parse_json(raw) == {"a": 1}

    def test_braces_inside_strings_do_not_break_parsing(self):
        raw = 'Пояснение.\n{"note": "значение с { и } внутри", "a": 2}'
        assert _parse_json(raw) == {"note": "значение с { и } внутри", "a": 2}

    def test_trailing_text_after_json(self):
        assert _parse_json('{"a": 1}\n\nЕсли нужно — уточню.') == {"a": 1}

    def test_json_array_alone_is_not_accepted(self):
        """Ожидается объект: массив верхнего уровня — не наш формат."""
        assert _parse_json("[1, 2, 3]") is None


class TestSafetyInvariants:
    async def test_requires_specialist_review_is_always_true(self, chunks):
        """Даже если модель попытается выставить False."""
        payload = json.loads(_valid_response("состоящих только из элементов, характеризующих товары"))
        payload["requires_specialist_review"] = False
        outcome = await RagAbsoluteGroundsAnalyzer(
            FakeLLM(json.dumps(payload, ensure_ascii=False)), chunks
        ).analyse(FACTS)

        assert outcome.result.requires_specialist_review is True

    async def test_confidence_never_reaches_one(self, chunks):
        payload = json.loads(_valid_response("состоящих только из элементов, характеризующих товары"))
        payload["findings"][0]["confidence"] = 1.0
        outcome = await RagAbsoluteGroundsAnalyzer(
            FakeLLM(json.dumps(payload, ensure_ascii=False)), chunks
        ).analyse(FACTS)

        assert outcome.result.findings[0].confidence < 1.0

    async def test_limitations_are_mandatory(self, chunks):
        """Ответ без указания ограничений анализа не принимается."""
        payload = json.loads(_valid_response("состоящих только из элементов, характеризующих товары"))
        payload["limitations"] = []
        outcome = await RagAbsoluteGroundsAnalyzer(
            FakeLLM(json.dumps(payload, ensure_ascii=False)), chunks
        ).analyse(FACTS)

        assert not outcome.is_conclusive
