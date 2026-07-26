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
import re
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
MAX_CONTEXT_CHUNKS = 8

# Запас на рассуждения модели плюс сам JSON-ответ: при лимите
# по умолчанию ответ обрывался на середине структуры.
MAX_RESPONSE_TOKENS = 12000

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

ПРИНЦИП СПЕЦИАЛИЗАЦИИ (обязательно учитывать):

Описательность и различительная способность оцениваются НЕ сами по себе,
а ТОЛЬКО в отношении конкретных заявленных товаров и услуг.

Одно и то же обозначение может быть описательным для одних товаров
и фантазийным для других:
  - «ЯБЛОКО» для свежих фруктов — описательное, указывает на вид товара;
  - «ЯБЛОКО» для компьютеров — произвольное, различительная способность есть.

Поэтому в каждом выводе о различительной способности обязательно
указывай, применительно к каким именно товарам или услугам сделан вывод,
и включай их в case_facts_used. Вывод «обозначение описательное» без
привязки к товарам неверен.
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

    # Корпус для оценки оснований отказа: нормы и подзаконные акты.
    # Справочник МКТУ сюда не входит — он нужен для подбора классов,
    # а в контексте оснований только вытесняет нормы.
    SOURCE_TYPES = frozenset({"law", "regulation"})

    def __init__(self, llm_provider: Any, chunks: list[StoredChunk]) -> None:
        self._llm = llm_provider
        legal_chunks = [c for c in chunks if c.source_type in self.SOURCE_TYPES]
        # Если типы не проставлены (старая индексация), работаем со всем
        # корпусом: лучше шум, чем пустой контекст.
        self._retriever = Retriever(legal_chunks or chunks)

    def _retrieve_grounds_context(self, facts: dict[str, Any]) -> list:
        """Отобрать нормы по каждому основанию отдельно.

        Один смешанный запрос не работает: факты дела перевешивают
        юридическую терминологию. На деле «программное обеспечение,
        SaaS» поднимало справочник классов МКТУ вместо статьи 1483.

        Поэтому поиск идёт по каждому основанию своим запросом —
        так же, как поверенный проверяет их по очереди, — а результаты
        объединяются без дублей.
        """
        case_hint = " ".join(
            str(facts.get(key) or "")
            for key in ("mark_text", "description", "goods_services")
        )

        # Запросы намеренно составлены из терминов норм, а не из фактов
        # дела: факты добавляются лишь как небольшая подсказка.
        ground_queries = [
            "различительная способность обозначения отсутствует",
            "описательное обозначение характеризует вид качество назначение товара",
            "вошло во всеобщее употребление общепринятый термин символ",
            "приобретённая различительная способность неохраняемые элементы",
            "ложное обозначение вводит потребителя в заблуждение изготовитель",
            "противоречит общественным интересам принципам гуманности и морали",
            "государственные символы гербы флаги официальные наименования",
            "объекты культурного наследия культурные ценности",
        ]

        selected: dict[str, Any] = {}
        for query in ground_queries:
            for hit in self._retriever.retrieve(f"{query} {case_hint[:120]}", top_k=2):
                # Один и тот же фрагмент может подойти нескольким основаниям.
                if hit.citation_id not in selected:
                    selected[hit.citation_id] = hit

        # Фрагменты с правовым якорем (статья/пункт) идут первыми:
        # для оценки оснований отказа норма важнее справочного материала,
        # даже если справочник совпал по словам лучше.
        ranked = sorted(
            selected.values(),
            key=lambda item: (bool(item.chunk.article), item.score),
            reverse=True,
        )
        return ranked[:MAX_CONTEXT_CHUNKS]

    async def analyse(self, facts: dict[str, Any]) -> AnalysisOutcome:
        retrieved = self._retrieve_grounds_context(facts)

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
        """Вызвать модель через интерфейс BaseLLMProvider.

        Поддерживается и упрощённый интерфейс ``complete(prompt)`` —
        он используется в тестах с подставными моделями.
        """
        try:
            if hasattr(self._llm, "generate"):
                from app.infrastructure.llm.base import LLMMessage

                response = await self._llm.generate(
                    messages=[
                        LLMMessage(role="system", content=SYSTEM_PROMPT),
                        LLMMessage(role="user", content=prompt),
                    ],
                    temperature=0.1,
                    max_tokens=MAX_RESPONSE_TOKENS,
                )
            else:
                response = await self._llm.complete(
                    prompt=prompt, system=SYSTEM_PROMPT, temperature=0.1
                )
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


# Markdown-блок с JSON в любом месте ответа, а не только в начале.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)


def _balanced_objects(text: str) -> list[str]:
    """Найти синтаксически цельные JSON-объекты в тексте.

    Наивный поиск «от первой { до последней }» ломается на моделях
    с рассуждениями: фигурные скобки встречаются и в пояснительном
    тексте, и тогда захватывается заведомо битый фрагмент. Здесь
    границы объекта считаются по балансу скобок, а строковые литералы
    и экранирование пропускаются, чтобы скобка внутри кавычек не
    сдвигала счётчик.
    """
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    objects.append(text[start : index + 1])
                    start = -1
    return objects


def _parse_json(raw: str) -> dict | None:
    """Извлечь JSON-объект из ответа модели.

    Модели с рассуждениями (reasoning) ведут себя по-разному от запроса
    к запросу: то отдают чистый JSON, то оборачивают его в markdown,
    то предваряют размышлениями. Поэтому разбор идёт по нарастающей —
    от самого строгого варианта к самому терпимому, и возвращается
    первый объект, который действительно разобрался.
    """
    if not raw:
        return None

    candidates: list[str] = [raw.strip()]

    # Содержимое markdown-блоков: обычно именно там лежит ответ.
    candidates.extend(match.strip() for match in _FENCE_RE.findall(raw))

    # Цельные объекты по балансу скобок — из блоков и из всего текста.
    for source in list(candidates):
        candidates.extend(_balanced_objects(source))

    for candidate in candidates:
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
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
