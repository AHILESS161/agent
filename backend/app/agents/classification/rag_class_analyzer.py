"""Подбор и проверка классов МКТУ с опорой на справочник.

Отдельный анализ со своим корпусом. Справочник МКТУ намеренно не
участвует в оценке оснований отказа: там он вытесняет нормы. И наоборот —
нормы не нужны при подборе классов.

Почему подбор классов важен не сам по себе. Различительная способность
оценивается только применительно к конкретным товарам: «ЯБЛОКО» для
свежих фруктов описательно, для компьютеров — произвольно. Ошибка
в классе меняет и вывод об охраноспособности, поэтому перечень товаров
проверяется до оценки оснований, а его результат передаётся в неё.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.legal.rag_analyzer import _parse_json
from app.core.logging import get_logger
from app.infrastructure.rag.citations import (
    MIN_QUOTE_WORDS_REFERENCE,
    verify_all,
)
from app.infrastructure.rag.retriever import (
    RetrievedChunk,
    Retriever,
    build_context,
)
from app.infrastructure.rag.store import StoredChunk

logger = get_logger(__name__)

MAX_CONTEXT_CHUNKS = 8

# Класс 35 — реклама, продвижение, услуги розничной и оптовой торговли.
# Он нужен почти любому, кто что-то продаёт, в том числе через интернет,
# но по запросу о самом товаре поиск его не находит: в описании класса
# нет ни «одежды», ни «игрушек». Модель же вправе ссылаться только на
# выданные фрагменты, поэтому этот раздел добавляется в контекст всегда.
ALWAYS_INCLUDE_CLASSES = ("Класс 35.",)

# Запас на рассуждения модели плюс сам JSON-ответ.
MAX_RESPONSE_TOKENS = 12000


class ClassSuggestion(BaseModel):
    """Предложенный класс МКТУ."""

    class_number: int = Field(ge=1, le=45)
    rationale: str = Field(min_length=10)
    # primary — основной для деятельности, secondary — сопутствующий,
    # borderline — спорный, требует решения специалиста.
    category: str = Field(default="primary")
    goods_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    citations: list[dict] = Field(default_factory=list)

    @property
    def is_services(self) -> bool:
        return self.class_number >= 35


class ClassAnalysisResult(BaseModel):
    """Результат подбора классов."""

    suggestions: list[ClassSuggestion] = Field(default_factory=list)
    summary: str = Field(min_length=10)
    # Товары, для которых класс подобрать не удалось.
    unclassified: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
    requires_specialist_review: bool = True


@dataclass
class ClassAnalysisOutcome:
    result: ClassAnalysisResult | None
    reason: str | None
    sources_used: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)

    @property
    def is_conclusive(self) -> bool:
        return self.result is not None


SYSTEM_PROMPT = """Ты — помощник патентного поверенного. Задача —
подобрать классы Международной классификации товаров и услуг (МКТУ)
для заявленных товаров и услуг.

СТРОГИЕ ПРАВИЛА:

1. Опирайся ТОЛЬКО на фрагменты из раздела ИСТОЧНИКИ.
2. Каждое предложение класса подтверждай цитатой из источника
   с указанием его source_id. Цитата — дословный фрагмент.
3. Классы 1–34 — товары, 35–45 — услуги. Не путай их.
4. Не придумывай номера и названия классов, которых нет в источниках.
5. Товары, для которых класс определить нельзя, помещай в unclassified,
   а не подбирай наугад.
6. Отвечай СТРОГО валидным JSON по схеме, без пояснений вокруг.

ВАЖНО. От выбора класса зависит и оценка охраноспособности: обозначение
описательно только относительно конкретных товаров. Поэтому по каждому
классу указывай, какие именно товары или услуги к нему отнесены.

ПОЛНОТА ПЕРЕЧНЯ.

Лучше предложить класс лишний раз, чем упустить нужный: специалист
уберёт ненужное сам, а недостающий класс после подачи заявки уже
не добавить — придётся подавать новую и платить пошлину заново.
Поэтому предлагай не только очевидный класс товара, но и смежные:
сопутствующие товары, материалы, из которых товар сделан, и услуги,
которыми заявитель этот товар продаёт или продвигает.

Класс 35 (реклама, продвижение, услуги розничной и оптовой торговли)
нужен почти всегда, если заявитель что-либо продаёт — в том числе
через интернет-магазин, маркетплейс или соцсети. Сегодня так работает
почти любой бизнес, поэтому проверяй этот класс отдельно и предлагай
его, если в деятельности есть продажа или продвижение.

Классы, в которых ты не уверен, помечай category: "borderline" —
специалист рассмотрит их отдельно. Уверенные ставь "primary",
сопутствующие — "secondary".
"""

USER_TEMPLATE = """ДЕЯТЕЛЬНОСТЬ ЗАЯВИТЕЛЯ:
Обозначение: {mark_text}
Описание деятельности: {business_description}
Заявленные товары и услуги: {goods_services}

ИСТОЧНИКИ (только на них можно ссылаться):

{context}

ЗАДАЧА:
Подбери классы МКТУ. По каждому классу укажи номер, обоснование,
отнесённые к нему товары или услуги и цитату из источника.

Верни JSON строго по схеме:
{schema}
"""


class RagNiceClassAnalyzer:
    """Подбор классов МКТУ по справочнику."""

    # Корпус справочника: сюда не входят нормы об основаниях отказа.
    SOURCE_TYPES = frozenset({"methodology"})

    def __init__(self, llm_provider: Any, chunks: list[StoredChunk]) -> None:
        self._llm = llm_provider
        nice_chunks = [c for c in chunks if c.source_type in self.SOURCE_TYPES]
        self._corpus = nice_chunks or chunks
        self._retriever = Retriever(self._corpus)
        self._has_corpus = bool(nice_chunks)

    def _with_trade_services(self, retrieved: list[Any]) -> list[Any]:
        """Дополнить выдачу разделами, нужными почти всегда.

        Пропустить класс 35 дороже, чем предложить лишний: после подачи
        заявки класс уже не добавить — нужна новая заявка и новая пошлина.

        Раздел берётся из корпуса по названию, а не поиском: слово
        «класс» есть в каждом фрагменте справочника, и поисковый запрос
        «Класс 35» ранжируется случайно.
        """
        present = " ".join(item.chunk.anchor for item in retrieved)

        for marker in ALWAYS_INCLUDE_CLASSES:
            if marker in present:
                continue
            chunk = next(
                (c for c in self._corpus if marker in c.anchor), None
            )
            if chunk is None:
                continue
            retrieved.append(RetrievedChunk(chunk=chunk, score=0.0))
        return retrieved

    async def analyse(self, facts: dict[str, Any]) -> ClassAnalysisOutcome:
        query = " ".join(
            str(facts.get(key) or "")
            for key in ("business_description", "goods_services", "mark_text")
        ).strip()

        if not query:
            return ClassAnalysisOutcome(
                result=None,
                reason="Не указаны товары, услуги или описание деятельности",
            )

        retrieved = self._retriever.retrieve(query, top_k=MAX_CONTEXT_CHUNKS)
        if not retrieved:
            return ClassAnalysisOutcome(
                result=None,
                reason="В справочнике МКТУ не найдено релевантных разделов",
            )

        retrieved = self._with_trade_services(retrieved)

        context, available_sources = build_context(retrieved)
        prompt = USER_TEMPLATE.format(
            mark_text=facts.get("mark_text") or "не указано",
            business_description=facts.get("business_description") or "не указано",
            goods_services=facts.get("goods_services") or "не указаны",
            context=context,
            schema=json.dumps(_compact_schema(), ensure_ascii=False, indent=2),
        )

        raw = await self._call_llm(prompt)
        if raw is None:
            return ClassAnalysisOutcome(
                result=None,
                reason="Модель не вернула ответ",
                sources_used=list(available_sources),
            )

        parsed = raw if isinstance(raw, dict) else _parse_json(raw)
        if parsed is None:
            return ClassAnalysisOutcome(
                result=None,
                reason="Ответ модели не является валидным JSON",
                sources_used=list(available_sources),
            )

        try:
            result = ClassAnalysisResult.model_validate(parsed)
        except ValidationError:
            return ClassAnalysisOutcome(
                result=None,
                reason="Ответ модели не соответствует требуемой схеме",
                sources_used=list(available_sources),
            )

        return self._verify(result, available_sources)

    def _verify(
        self, result: ClassAnalysisResult, available_sources: dict[str, str]
    ) -> ClassAnalysisOutcome:
        """Отбросить предложения без подтверждённой цитаты."""
        confirmed: list[ClassSuggestion] = []
        rejected: list[dict] = []

        for suggestion in result.suggestions:
            # Цитата из МКТУ — название товара, а не положение нормы.
            report = verify_all(
                suggestion.citations,
                available_sources,
                min_words=MIN_QUOTE_WORDS_REFERENCE,
            )
            if report.has_any_trustworthy_source:
                verified = {c.quote for c in report.verified}
                suggestion.citations = [
                    c for c in suggestion.citations if c.get("quote") in verified
                ]
                confirmed.append(suggestion)
            else:
                rejected.append(
                    {
                        "class_number": suggestion.class_number,
                        "rationale": suggestion.rationale,
                        "goods_services": suggestion.goods_services,
                        "reason": (
                            "цитата не найдена в справочнике дословно"
                        ),
                    }
                )
                logger.info(
                    "Предложение класса отброшено: цитаты не подтверждены",
                    class_number=suggestion.class_number,
                )

        verification = {
            "suggested_by_model": len(result.suggestions),
            "confirmed": len(confirmed),
            "rejected": rejected,
        }

        if not confirmed:
            # Предложения показываются специалисту даже без подтверждённой
            # цитаты: решение за ним, а молчание системы полезнее не делает.
            return ClassAnalysisOutcome(
                result=None,
                reason=(
                    "Ни одно предложение класса не подтверждено справочником. "
                    "Предложенные варианты показаны отдельно — решение "
                    "за специалистом."
                    if result.suggestions
                    else "Модель не предложила классов"
                ),
                sources_used=list(available_sources),
                verification=verification,
            )

        result.suggestions = confirmed
        return ClassAnalysisOutcome(
            result=result,
            reason=None,
            sources_used=list(available_sources),
            verification=verification,
        )

    async def _call_llm(self, prompt: str) -> str | dict[str, Any] | None:
        try:
            from app.infrastructure.llm.base import LLMMessage

            messages = [
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(role="user", content=prompt),
            ]

            # Просим провайдер применить JSON Schema на уровне API. Простая
            # инструкция «верни JSON» иногда даёт синтаксически корректный,
            # но нестабильный по структуре ответ. Для GigaChat это особенно
            # заметно при повторных прогонах одного и того же дела.
            if hasattr(self._llm, "generate_structured"):
                response = await self._llm.generate_structured(
                    messages=messages,
                    output_schema=ClassAnalysisResult.model_json_schema(),
                    temperature=0.1,
                )
            elif hasattr(self._llm, "generate"):

                response = await self._llm.generate(
                    messages=messages,
                    temperature=0.1,
                    # Модели с рассуждениями тратят часть бюджета на
                    # размышления. При лимите по умолчанию ответ
                    # обрывался на середине JSON.
                    max_tokens=MAX_RESPONSE_TOKENS,
                )
            else:
                response = await self._llm.complete(
                    prompt=prompt, system=SYSTEM_PROMPT, temperature=0.1
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Ошибка вызова LLM",
                error_type=type(exc).__name__,
                error=str(exc) or repr(exc),
            )
            return None

        if isinstance(response, (str, dict)):
            return response
        return getattr(response, "content", None) or getattr(response, "text", None)


def _compact_schema() -> dict:
    return {
        "suggestions": [
            {
                "class_number": "число от 1 до 45",
                "rationale": "почему этот класс подходит",
                "category": "primary | secondary | borderline",
                "goods_services": ["товар или услуга, отнесённые к классу"],
                "confidence": "число от 0 до 1",
                "citations": [
                    {
                        "source_id": "идентификатор из раздела ИСТОЧНИКИ",
                        "quote": "дословный фрагмент источника",
                        "anchor": "раздел справочника",
                    }
                ],
            }
        ],
        "summary": "краткий вывод",
        "unclassified": ["товар, для которого класс определить не удалось"],
        "limitations": ["ограничения подбора — обязательное поле"],
        "requires_specialist_review": True,
    }
