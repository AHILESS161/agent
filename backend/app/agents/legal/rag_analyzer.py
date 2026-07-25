"""Анализ обозначения по абсолютным основаниям с опорой на базу знаний.

Зачем RAG. Модель получает не «вспомни закон», а конкретные фрагменты
нормативных материалов с идентификаторами. Это даёт две вещи:

1. **Точность на слабых моделях.** Небольшая модель плохо помнит статьи
   ГК РФ, но хорошо работает с текстом, который лежит перед ней.
2. **Проверяемость.** Каждый вывод обязан ссылаться на выданный фрагмент,
   и ссылка проверяется дословно. Выдуманная норма не пройдёт.

Порядок работы:
    факты дела → поиск по базе знаний → контекст с source_id
    → строгий JSON от модели → валидация схемой → проверка цитат
    → выводы без подтверждённого источника отбрасываются

Если после проверки не осталось ни одного обоснованного вывода,
возвращается «Недостаточно подтверждённых данных для вывода.»
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.infrastructure.rag.citations import verify_all
from app.infrastructure.rag.retriever import Retriever, build_context
from app.infrastructure.rag.store import StoredChunk
from app.schemas.analysis import AnalysisResult, InsufficientData, RiskLevel

logger = get_logger(__name__)

# Ограничение на объём контекста: слабые модели теряются в длинном тексте.
MAX_CONTEXT_CHUNKS = 6

SYSTEM_PROMPT = """Ты — помощник патентного поверенного. Твоя задача —
предварительная оценка рисков регистрации товарного знака по абсолютным
основаниям (ГК РФ, статья 1483).

СТРОГИЕ ПРАВИЛА:

1. Опирайся ТОЛЬКО на фрагменты, приведённые в разделе ИСТОЧНИКИ.
   Не используй знания, которых нет в источниках.
2. Каждый вывод обязан содержать цитату из источника с его source_id.
   Цитата — дословный фрагмент текста источника, не пересказ.
3. Если источников недостаточно для вывода — не делай вывод.
   Лучше вернуть пустой список findings, чем необоснованный вывод.
4. Не придумывай номера статей, пунктов, судебную практику и реквизиты.
5. Не давай категоричных заключений о том, что знак будет зарегистрирован.
   Это предварительная оценка, а не юридическое заключение.
6. Отвечай СТРОГО валидным JSON по указанной схеме, без пояснений вокруг.
"""

USER_TEMPLATE = """ФАКТЫ ДЕЛА:
Обозначение: {mark_text}
Вид знака: {mark_type}
Описание: {description}
Товары и услуги: {goods_services}
Классы МКТУ: {classes}

ИСТОЧНИКИ (только на них можно ссылаться):

{context}

ЗАДАЧА:
Оцени риски отказа по абсолютным основаниям. Для каждого установленного
риска укажи категорию, уровень, правовое основание, объяснение, факты
дела, на которых основан вывод, и цитаты из источников с их source_id.

Верни JSON строго по схеме:
{schema}
"""


@dataclass
class AnalysisOutcome:
    """Результат анализа вместе с диагностикой проверки."""

    result: AnalysisResult | None
    insufficient: InsufficientData | None
    verification: dict[str, Any]
    sources_used: list[str]
    llm_raw: str | None = None

    @property
    def is_conclusive(self) -> bool:
        return self.result is not None


class RagAbsoluteGroundsAnalyzer:
    """Анализ абсолютных оснований с проверкой цитат."""

    def __init__(self, llm_provider: Any, chunks: list[StoredChunk]) -> None:
        self._llm = llm_provider
        self._retriever = Retriever(chunks)

    def _build_query(self, facts: dict[str, Any]) -> str:
        """Запрос к базе знаний строится из фактов дела."""
        parts = [
            str(facts.get("mark_text") or ""),
            str(facts.get("description") or ""),
            str(facts.get("goods_services") or ""),
            # Терминология оснований помогает поднять релевантные нормы.
            "различительная способность описательность введение в заблуждение "
            "общественные интересы мораль государственная символика "
            "всеобщее употребление отказ в регистрации",
        ]
        return " ".join(p for p in parts if p)

    async def analyse(self, facts: dict[str, Any]) -> AnalysisOutcome:
        retrieved = self._retriever.retrieve(
            self._build_query(facts), top_k=MAX_CONTEXT_CHUNKS
        )

        if not retrieved:
            return AnalysisOutcome(
                result=None,
                insufficient=InsufficientData(
                    reason="В базе знаний не найдено релевантных материалов",
                    missing_data=["Нормативные материалы по абсолютным основаниям"],
                ),
                verification={"total": 0, "verified": 0, "rejected": 0},
                sources_used=[],
            )

        context, available_sources = build_context(retrieved)

        prompt = USER_TEMPLATE.format(
            mark_text=facts.get("mark_text") or "не указано",
            mark_type=facts.get("mark_type") or "не указан",
            description=facts.get("description") or "не указано",
            goods_services=facts.get("goods_services") or "не указаны",
            classes=facts.get("classes") or "не указаны",
            context=context,
            schema=json.dumps(
                _compact_schema(), ensure_ascii=False, indent=2
            ),
        )

        raw = await self._call_llm(prompt)
        if raw is None:
            return AnalysisOutcome(
                result=None,
                insufficient=InsufficientData(
                    reason="Модель не вернула ответ",
                    missing_data=["Ответ языковой модели"],
                ),
                verification={"total": 0, "verified": 0, "rejected": 0},
                sources_used=list(available_sources),
            )

        parsed = _parse_json(raw)
        if parsed is None:
            logger.warning("Модель вернула невалидный JSON")
            return AnalysisOutcome(
                result=None,
                insufficient=InsufficientData(
                    reason="Ответ модели не является валидным JSON",
                ),
                verification={"total": 0, "verified": 0, "rejected": 0},
                sources_used=list(available_sources),
                llm_raw=raw[:2000],
            )

        try:
            result = AnalysisResult.model_validate(parsed)
        except ValidationError as exc:
            logger.warning("Ответ модели не прошёл валидацию схемы", errors=exc.error_count())
            return AnalysisOutcome(
                result=None,
                insufficient=InsufficientData(
                    reason="Ответ модели не соответствует требуемой схеме",
                ),
                verification={"total": 0, "verified": 0, "rejected": 0},
                sources_used=list(available_sources),
                llm_raw=raw[:2000],
            )

        return self._verify(result, available_sources)

    def _verify(
        self, result: AnalysisResult, available_sources: dict[str, str]
    ) -> AnalysisOutcome:
        """Отбросить выводы, не подтверждённые источниками."""
        confirmed = []
        total_checks = 0
        total_verified = 0
        rejected_details: list[dict] = []

        for finding in result.findings:
            report = verify_all(
                [c.model_dump() for c in finding.citations], available_sources
            )
            total_checks += report.total
            total_verified += len(report.verified)

            finding.citations_verified = report.has_any_trustworthy_source
            finding.verification_summary = report.summary()

            if report.has_any_trustworthy_source:
                # Оставляем только подтверждённые цитаты: непроверенные
                # ссылки не должны попадать в отчёт.
                verified_quotes = {c.quote for c in report.verified}
                finding.citations = [
                    c for c in finding.citations if c.quote in verified_quotes
                ]
                confirmed.append(finding)
            else:
                rejected_details.append(
                    {
                        "category": finding.category.value,
                        "reason": "нет подтверждённых цитат",
                        "checks": report.summary(),
                    }
                )
                logger.info(
                    "Вывод отброшен: цитаты не подтверждены",
                    category=finding.category.value,
                )

        verification = {
            "citations_total": total_checks,
            "citations_verified": total_verified,
            "findings_returned_by_model": len(result.findings),
            "findings_confirmed": len(confirmed),
            "findings_rejected": rejected_details,
        }

        if not confirmed:
            return AnalysisOutcome(
                result=None,
                insufficient=InsufficientData(
                    reason=(
                        "Ни один вывод не подтверждён источниками из базы знаний"
                        if result.findings
                        else "Модель не установила рисков по имеющимся источникам"
                    ),
                    missing_data=result.missing_data,
                ),
                verification=verification,
                sources_used=list(available_sources),
            )

        result.findings = confirmed
        # Итоговый уровень пересчитывается по оставшимся выводам:
        # оценка модели могла опираться на отброшенные.
        result.overall_risk = _max_level(confirmed)
        return AnalysisOutcome(
            result=result,
            insufficient=None,
            verification=verification,
            sources_used=list(available_sources),
        )

    async def _call_llm(self, prompt: str) -> str | None:
        try:
            response = await self._llm.complete(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                temperature=0.1,
            )
        except TypeError:
            # Провайдеры с иной сигнатурой (позиционные аргументы).
            try:
                response = await self._llm.complete(prompt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ошибка вызова LLM", error=str(exc))
                return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка вызова LLM", error=str(exc))
            return None

        if isinstance(response, str):
            return response
        return getattr(response, "content", None) or getattr(response, "text", None)


def _max_level(findings: list) -> RiskLevel:
    order = [RiskLevel.low, RiskLevel.medium, RiskLevel.high, RiskLevel.critical]
    highest = RiskLevel.low
    for finding in findings:
        if order.index(finding.level) > order.index(highest):
            highest = finding.level
    return highest


def _parse_json(raw: str) -> dict | None:
    """Извлечь JSON из ответа модели.

    Слабые модели часто оборачивают JSON в markdown-блок или
    добавляют пояснение до и после.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _compact_schema() -> dict:
    """Компактное описание схемы для промпта.

    Полная JSON Schema от Pydantic слишком громоздка и сбивает
    небольшие модели.
    """
    return {
        "overall_risk": "low | medium | high | critical",
        "summary": "краткий вывод, не менее 20 символов",
        "findings": [
            {
                "category": (
                    "no_distinctiveness | descriptive | common_use | misleading | "
                    "against_public_interest | official_symbols | conflicting_mark | other"
                ),
                "level": "low | medium | high | critical",
                "legal_basis": "например: ГК РФ ст. 1483 п. 1",
                "explanation": "объяснение вывода",
                "case_facts_used": ["факт дела"],
                "citations": [
                    {
                        "source_id": "идентификатор из раздела ИСТОЧНИКИ",
                        "quote": "дословный фрагмент источника",
                        "anchor": "например: ст. 1483, п. 1",
                    }
                ],
                "confidence": "число от 0 до 1",
                "missing_data": ["чего не хватает"],
                "recommended_action": "рекомендация",
            }
        ],
        "limitations": ["ограничения анализа — обязательное поле"],
        "missing_data": ["общие недостающие данные"],
        "requires_specialist_review": True,
    }
