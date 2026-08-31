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
MAX_RESPONSE_TOKENS = 16000

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
7. В findings включай только УСТАНОВЛЕННЫЕ обстоятельства, которые повышают риск
   отказа. Успешное прохождение критерия (например, «не содержит символов» или
   «не вводит в заблуждение») не является риском и не должно попадать в findings.
8. Общая норма доказывает только содержание правила, но не факт его применимости
   к обозначению. Для объектов культурного наследия, официальных символов и
   наименований нужен источник, который прямо связывает именно заявленное
   обозначение с конкретным охраняемым объектом. Без такого источника вывод не делай.
9. Если в фактах указано «Изображение приложено: да», не добавляй изображение знака
   в missing_data. Оцени словесные элементы, описание и цвета; ограничения оценки
   самой графики укажи в limitations.
10. Сам по себе факт, что обозначение состоит из обычных слов, НЕ доказывает
    отсутствие различительной способности. Оценивай сочетание целиком.
11. Описательным считай только обозначение, которое прямо и непосредственно
    сообщает потребителю вид, качество, свойство, назначение, место или способ
    оказания именно заявленных товаров или услуг. Ассоциация, рекламный намёк,
    метафора либо рассуждение вида «может восприниматься как» недостаточны.
12. Не превращай желаемый образ бренда или характер обслуживания в юридически
    установленное свойство услуги. Например, слова «дружелюбный сосед» сами по
    себе не описывают ремонт компьютеров и не означают «дружелюбный сервис» или
    оказание услуги «по-соседски» без дополнительных подтверждённых фактов.
13. Комбинированное обозначение оценивай в целом: словесную часть, изображение
    и их композицию. Описательный или неохраняемый элемент сам по себе не означает,
    что всему комбинированному знаку будет отказано в регистрации.
14. Изображение заявленного товара, результата или предмета обслуживания обычно
    означает лишь возможное отсутствие самостоятельной охраны такого элемента.
    Не называй его вводящим в заблуждение только потому, что он связан с товарами
    или услугами заявителя. Для вывода о введении в заблуждение нужна конкретная
    ложная и правдоподобная информация о товаре, услуге, изготовителе или месте
    происхождения.
15. Не подменяй конкретный заявленный перечень широким заголовком класса МКТУ.
    Анализируй только товары и услуги, перечисленные в фактах дела.
16. В summary объясняй вывод как профессиональный юрист обычному заявителю:
    сначала практический итог, затем причина и действие. Не упоминай модель,
    промпт, RAG, коэффициенты, таймауты, JSON и внутренние этапы системы.
17. Проверяй подп. 2 п. 3 ст. 1483 (общественные интересы, гуманность и мораль)
    ОТДЕЛЬНО от описательности и различительной способности. У одного обозначения
    может быть несколько самостоятельных оснований отказа. Для анатомической или
    сексуальной лексики различай нейтральный медицинский термин, разговорное слово,
    бранное выражение и непристойный контекст. Не объявляй любое анатомическое слово
    аморальным автоматически, но обязательно оцени его значение, форму подачи и связь
    с конкретными товарами и услугами.
18. Норма в источнике подтверждает юридический критерий; источник не обязан дословно
    называть исследуемое слово. Требование о прямой связи с конкретным объектом из
    правила 8 относится к официальным символам и объектам культурного наследия, а не
    запрещает смысловую оценку самого заявленного слова по общепринятому значению.
19. В summary обязательно назови обозначение, конкретные товары или услуги, главное
    основание риска и практическое последствие. Не заменяй конкретный вывод словами
    «есть элементы, связанные с товарами».
20. В missing_data указывай только факты о заявке, которые действительно может
    предоставить заявитель: изображение, точный перечень товаров, значение
    иностранного слова, сведения об использовании и т. п. Отсутствие в ИСТОЧНИКАХ
    решения Роспатента или суда с тем же самым словом, словарной статьи именно об
    этом слове либо идентичного примера НЕ является недостающим фактом дела и не
    освобождает от предварительной оценки по приведённому юридическому критерию.
21. Если риск зависит от спорного восприятия слова, не уклоняйся от вывода. Дай
    осторожную предварительную оценку medium, прямо назови неопределённость и
    рекомендуй ручную проверку. Для вывода high или critical должны быть конкретные
    признаки из фактов дела, а не только возможность неприятной ассоциации.
22. Нейтральный анатомический или медицинский термин сам по себе не является
    нецензурным словом. Однако оцени отдельно, может ли его использование в качестве
    заметного обозначения для несвязанных товаров восприниматься как непристойное.
    Если такое восприятие спорно, это предварительный средний риск по подп. 2 п. 3
    ст. 1483, а не описательность и не автоматически установленный отказ.
23. Если после проверки всех критериев неблагоприятных обстоятельств нет, верни
    overall_risk="low", пустой findings, содержательный summary и пустой
    missing_data. Не подменяй итог запросом дополнительной судебной практики.
24. Для основания о морали укажи, какое именно содержание может быть признано
    непристойным или какой конкретный принцип затронут. Общая ссылка на мораль без
    связи с обозначением недостаточна.

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
Заявленные цвета: {colors}
Изображение приложено: {image_attached}
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


SUBSTANTIVE_RETRY_INSTRUCTION = """

ПОВТОРНАЯ ЮРИДИЧЕСКАЯ ПРОВЕРКА:
Предыдущая попытка не дала практического вывода и запросила дополнительные
правовые источники или идентичные прецеденты. Это не сведения, которые должен
предоставлять заявитель. Повтори анализ по уже приведённым нормам и фактам.

- Не требуй дело Роспатента, суда, словарь или перечень, где дословно названо
  исследуемое обозначение.
- Самостоятельно сопоставь обычное значение слов с юридическими критериями.
- Если восприятие спорно, верни обоснованный medium risk и прямо объясни границу
  неопределённости; не возвращай незавершённый анализ.
- Если подтверждённых рисков нет, верни low risk, findings=[] и missing_data=[].
- Сохрани строгий JSON и дословные цитаты из выданных ИСТОЧНИКОВ.
"""


_NON_ACTIONABLE_RESEARCH_GAP_MARKERS = (
    "практик",
    "пример",
    "решен",
    "словар",
    "источник",
    "перечень нецензур",
    "перечень бран",
    "аналогичн",
)


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
        self._last_model: str | None = None
        self._last_used_fallback = False
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

        # Резервируем хотя бы один фрагмент на каждое проверяемое основание.
        # Раньше все результаты смешивались и затем обрезались по общему score:
        # несколько похожих фрагментов об описательности могли полностью вытеснить
        # норму о морали или введении в заблуждение.
        hit_groups: list[list[Any]] = []
        for query in ground_queries:
            hits = self._retriever.retrieve(f"{query} {case_hint[:120]}", top_k=2)
            hit_groups.append(
                sorted(
                    hits,
                    key=lambda item: (bool(item.chunk.article), item.score),
                    reverse=True,
                )
            )

        selected: dict[str, Any] = {}
        for position in range(2):
            for hits in hit_groups:
                if position >= len(hits):
                    continue
                hit = hits[position]
                selected.setdefault(hit.citation_id, hit)
                if len(selected) >= MAX_CONTEXT_CHUNKS:
                    return list(selected.values())
        return list(selected.values())

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
            colors=facts.get("colors") or "не указаны",
            image_attached="да" if facts.get("image_attached") else "нет",
            goods_services=facts.get("goods_services") or "не указаны",
            classes=facts.get("classes") or "не указаны",
            context=context,
            schema=json.dumps(
                _compact_schema(), ensure_ascii=False, indent=2
            ),
        )

        raw = await self._call_llm(prompt)
        outcome = self._interpret_response(raw, available_sources, facts)

        # Иногда primary возвращает формально корректный JSON, но вместо оценки
        # просит у заявителя судебную практику, словарь или идентичный пример.
        # Это не отсутствующие факты заявки. Даём DeepSeek второй, явно
        # сфокусированный проход до переключения на резервного провайдера.
        primary_retry_attempted = False
        first_reason = outcome.insufficient.reason if outcome.insufficient else None
        if (
            self._needs_substantive_retry(outcome)
            and not self._last_used_fallback
            and callable(getattr(self._llm, "generate", None))
        ):
            primary_retry_attempted = True
            retry_raw = await self._call_llm(prompt + SUBSTANTIVE_RETRY_INSTRUCTION)
            retry_outcome = self._interpret_response(
                retry_raw, available_sources, facts
            )
            retry_outcome.verification["primary_retry_attempted"] = True
            retry_outcome.verification["primary_first_reason"] = first_reason
            outcome = retry_outcome

        # Сетевая ошибка перехватывается самим FallbackLLMProvider. Здесь
        # обрабатывается другой важный случай: primary ответил HTTP 200, но
        # вернул оборванный JSON, неверную схему либо юридически непроверяемые
        # ссылки. Такой ответ тоже нельзя считать успешным — повторяем запрос
        # непосредственно через GigaChat.
        retryable_reasons = {
            "Модель не вернула ответ",
            "Ответ модели не является валидным JSON",
            "Ответ модели не соответствует требуемой схеме",
            "Ни один вывод не подтверждён источниками из базы знаний",
            "Модель не установила рисков по имеющимся источникам",
        }
        reason = outcome.insufficient.reason if outcome.insufficient else None
        can_use_explicit_fallback = (
            not outcome.is_conclusive
            and reason in retryable_reasons
            and not self._last_used_fallback
            and callable(getattr(self._llm, "generate_fallback", None))
        )
        if can_use_explicit_fallback:
            fallback_raw = await self._call_llm(prompt, use_fallback=True)
            fallback_outcome = self._interpret_response(
                fallback_raw, available_sources, facts
            )
            fallback_outcome.verification["fallback_attempted"] = True
            fallback_outcome.verification["fallback_provider"] = "gigachat"
            if primary_retry_attempted:
                fallback_outcome.verification["primary_retry_attempted"] = True
                fallback_outcome.verification["primary_first_reason"] = first_reason
            outcome = fallback_outcome

        outcome.verification["llm_model"] = self._last_model
        outcome.verification["llm_fallback_used"] = self._last_used_fallback
        return outcome

    @staticmethod
    def _needs_substantive_retry(outcome: AnalysisOutcome) -> bool:
        """Отличить пробел модели от реально отсутствующих фактов заявки."""
        if outcome.is_conclusive or outcome.insufficient is None:
            return False
        if (
            outcome.insufficient.reason
            != "Модель не установила рисков по имеющимся источникам"
        ):
            return False
        missing = [
            str(item).strip().lower()
            for item in outcome.insufficient.missing_data
            if str(item).strip()
        ]
        return bool(missing) and all(
            any(marker in item for marker in _NON_ACTIONABLE_RESEARCH_GAP_MARKERS)
            for item in missing
        )

    def _interpret_response(
        self,
        raw: str | None,
        available_sources: dict[str, str],
        facts: dict[str, Any],
    ) -> AnalysisOutcome:
        """Разобрать, проверить и юридически отфильтровать один ответ LLM."""
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

        return self._verify(result, available_sources, facts)

    def _verify(
        self,
        result: AnalysisResult,
        available_sources: dict[str, str],
        facts: dict[str, Any],
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
                finding_text = " ".join((
                    finding.legal_basis,
                    finding.explanation,
                    *finding.case_facts_used,
                )).lower()
                mark_text = re.sub(r"\W+", " ", str(facts.get("mark_text") or "").lower()).strip()
                verified_text = re.sub(r"\W+", " ", " ".join(verified_quotes).lower())
                fact_specific_ground = any(token in finding_text for token in (
                    "культурн", "наследи", "официальн", "государственн", "герб", "флаг",
                ))
                negative_non_risk = any(phrase in finding_text for phrase in (
                    "обеспечивает различительную",
                    "является фантазийн",
                    "не содержит бран",
                    "не содержит государствен",
                    "не включает государствен",
                    "отсутствуют географическ",
                    "не вводит потребител",
                    "не противоречит обществен",
                ))
                speculative_descriptive = (
                    finding.category.value == "descriptive"
                    and any(phrase in finding_text for phrase in (
                        "может восприниматься",
                        "может указывать",
                        "может ассоциироваться",
                        "ассоциац",
                        "намёк",
                        "по-соседски",
                        "состоит из общеупотребительных слов",
                        "указывает на предполагаемого покупателя",
                    ))
                )
                source_names_mark = bool(mark_text and mark_text in verified_text)
                if negative_non_risk or speculative_descriptive or (fact_specific_ground and not source_names_mark):
                    rejected_details.append({
                        "category": finding.category.value,
                        "reason": (
                            "успешная проверка не является риском"
                            if negative_non_risk
                            else "описательность основана на предположении, а не на прямой связи с услугами"
                            if speculative_descriptive
                            else "источник не связывает обозначение с конкретным охраняемым объектом"
                        ),
                        "checks": report.summary(),
                    })
                    continue
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

        # Модель иногда просит уже приложенное изображение. Это не реальный
        # пробел во входных данных и не должно превращать всю проверку в
        # «незавершённую».
        if facts.get("image_attached"):
            result.missing_data = [
                item for item in result.missing_data
                if "изображен" not in item.lower()
            ]

        if not confirmed:
            # Пустой список findings является штатным ответом на инструкцию
            # «включай только установленные риски». Если модель не заявляла
            # рисков и после очистки фактически отсутствующих данных пробелов
            # нет, абсолютные основания проверены с низким предварительным
            # риском. Это отличается от ситуации, когда вывод был заявлен, но
            # его цитаты не прошли проверку — такой результат остаётся
            # неопределённым.
            speculative_only = bool(rejected_details) and all(
                item["reason"]
                == "описательность основана на предположении, а не на прямой связи с услугами"
                for item in rejected_details
            )
            if (not result.findings or speculative_only) and not result.missing_data:
                result.overall_risk = RiskLevel.low
                result.findings = []
                if speculative_only:
                    result.summary = (
                        "По представленным данным обозначение не описывает прямо "
                        "вид, качество или назначение заявленных товаров и услуг. "
                        "Подтверждённых абсолютных оснований для отказа не установлено."
                    )
                verification["no_adverse_findings"] = True
                return AnalysisOutcome(
                    result=result,
                    insufficient=None,
                    verification=verification,
                    sources_used=list(available_sources),
                )
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

    async def _call_llm(self, prompt: str, *, use_fallback: bool = False) -> str | None:
        """Вызвать модель через интерфейс BaseLLMProvider.

        Поддерживается и упрощённый интерфейс ``complete(prompt)`` —
        он используется в тестах с подставными моделями.
        """
        try:
            if hasattr(self._llm, "generate"):
                from app.infrastructure.llm.base import LLMMessage

                method = (
                    self._llm.generate_fallback
                    if use_fallback and hasattr(self._llm, "generate_fallback")
                    else self._llm.generate
                )
                response = await method(
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
            self._last_model = getattr(self._llm, "model", None)
            self._last_used_fallback = use_fallback
            return response
        self._last_model = getattr(response, "model", None) or getattr(
            self._llm, "model", None
        )
        used_fallback = getattr(self._llm, "response_used_fallback", None)
        self._last_used_fallback = bool(
            use_fallback
            or (callable(used_fallback) and used_fallback(response))
        )
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
