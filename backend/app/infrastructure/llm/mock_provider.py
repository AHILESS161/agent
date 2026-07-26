"""
Mock LLM provider that returns canned, realistic responses for trademark analysis scenarios.
Used for development, testing, and offline operation.
"""
import json
import re
import time
from typing import Any

from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage, LLMResponse


# ---------------------------------------------------------------------------
# Canned structured responses keyed by pattern keywords
# ---------------------------------------------------------------------------

_CANNED_STRUCTURED: dict[str, Any] = {
    "intake": {
        "is_complete": False,
        "missing_fields": [
            {
                "field": "applicant.email",
                "reason": "Электронный адрес заявителя обязателен для уведомлений",
                "who_provides": "client",
                "criticality": "blocking",
            },
            {
                "field": "mark.image_file",
                "reason": "Изображение товарного знака не приложено",
                "who_provides": "client",
                "criticality": "blocking",
            },
        ],
        "completeness_score": 0.72,
        "blocking_gaps": 2,
        "non_blocking_gaps": 1,
        "recommendation": "Запросить у клиента недостающие документы перед подачей заявки",
    },
    "absolute_grounds": {
        "has_absolute_grounds": False,
        "grounds_found": [],
        "risk_level": "low",
        "analysis": (
            "Обозначение является фантазийным словом, не несёт описательного характера "
            "в отношении заявленных товаров/услуг. Признаков обманности не выявлено. "
            "Государственные символы отсутствуют."
        ),
        "articles_triggered": [],
        "recommendation": "Абсолютных оснований для отказа не обнаружено. Рекомендуется продолжить экспертизу.",
        "confidence": 0.87,
    },
    "relative_grounds": {
        "has_relative_grounds": True,
        "conflicts_found": [
            {
                "conflict_mark": "АЛЬФА",
                "registration_number": "123456",
                "classes": [36],
                "similarity_type": ["visual", "phonetic"],
                "similarity_score": 0.78,
                "owner": 'ОАО "Альфа-Банк"',
                "risk": "high",
            }
        ],
        "overall_risk": "medium",
        "recommendation": "Обнаружены схожие обозначения. Рекомендуется провести детальный анализ вероятности смешения.",
        "confidence": 0.82,
    },
    "nice_class": {
        "primary_classes": [
            {"class": 35, "rationale": "Реклама, управление предприятием, деловые операции"},
            {"class": 42, "rationale": "Разработка программного обеспечения, IT-услуги"},
        ],
        "secondary_classes": [
            {"class": 9, "rationale": "Программное обеспечение, электронные устройства"}
        ],
        "borderline_classes": [
            {
                "class": 38,
                "rationale": "Телекоммуникации — применимо если предоставляются коммуникационные услуги",
                "condition": "зависит от описания услуг",
            }
        ],
        "recommended_class_description": {
            35: "Услуги в области рекламы; продвижение товаров и услуг в сети Интернет",
            42: "Разработка и сопровождение программного обеспечения; создание веб-сайтов",
        },
        "confidence": 0.91,
    },
    "conflict_query": {
        "queries": [
            {
                "type": "exact",
                "value": "МАРКА",
                "description": "Точное совпадение наименования",
            },
            {
                "type": "fuzzy",
                "value": "МАРКА~",
                "description": "Нечёткий поиск с допуском ошибок",
            },
            {
                "type": "phonetic",
                "value": "МARKA",
                "description": "Фонетический эквивалент",
            },
            {
                "type": "transliteration",
                "value": "MARKA",
                "description": "Транслитерация на латиницу",
            },
            {
                "type": "semantic",
                "value": "знак бренд торговый",
                "description": "Семантически схожие понятия",
            },
        ],
        "suggested_classes": [35, 42],
        "search_strategy": "comprehensive",
    },
    "conflict_analysis": {
        "total_conflicts": 2,
        "high_risk_conflicts": 1,
        "medium_risk_conflicts": 1,
        "low_risk_conflicts": 0,
        "overall_risk": "medium",
        "detailed_analysis": [
            {
                "record_id": "RU0012345",
                "mark": "ИННОВАЦИЯ",
                "visual_similarity": 0.85,
                "phonetic_similarity": 0.90,
                "semantic_similarity": 0.60,
                "goods_services_overlap": True,
                "risk_level": "high",
                "likelihood_of_confusion": True,
                "owner": 'ООО "Инновационные технологии"',
                "recommendation": "Высокий риск смешения — рекомендуется изменить обозначение или оспорить регистрацию",
            }
        ],
        "recommended_action": "human_review",
        "confidence": 0.79,
    },
    "recommendation": {
        "memo_type": "lawyer_review",
        "summary": "Заявка требует доработки перед подачей в Роспатент",
        "key_findings": [
            "Абсолютных оснований для отказа не выявлено",
            "Обнаружено 1 потенциально конфликтное обозначение высокого риска",
            "Классификация МКТУ уточнена — добавлен класс 42",
        ],
        "risk_assessment": {
            "absolute_grounds_risk": "low",
            "relative_grounds_risk": "medium",
            "overall_risk": "medium",
        },
        "recommended_actions": [
            {
                "priority": 1,
                "action": "Провести анализ вероятности смешения с обозначением RU0012345",
                "responsible": "lawyer",
            },
            {
                "priority": 2,
                "action": "Уточнить перечень товаров/услуг по классу 42",
                "responsible": "agent",
            },
        ],
        "proceed_to_filing": False,
        "confidence": 0.85,
    },
    "document_mapping": {
        "mapped_fields": {
            "заявитель_наименование": "ООО «Пример»",
            "заявитель_адрес": "119991, г. Москва, ул. Ленина, д. 1",
            "заявитель_огрн": "1234567890123",
            "заявитель_инн": "7712345678",
            "обозначение_вид": "словесное",
            "мкту_классы": "35, 42",
            "описание_товаров_услуг": "Услуги в области рекламы; разработка ПО",
        },
        "unmapped_fields": ["заявитель_представитель"],
        "template_id": "form_заявка_роспатент_2023",
        "confidence": 0.95,
        "warnings": [],
    },
    "client_notification": {
        "subject": "Запрос дополнительных сведений по заявке на регистрацию товарного знака",
        "body": (
            "Уважаемый Клиент,\n\n"
            "В ходе обработки Вашей заявки на регистрацию товарного знака "
            "нами были выявлены следующие недостающие сведения, без которых "
            "подача заявки в Роспатент невозможна:\n\n"
            "1. Изображение товарного знака (файл в формате JPG/PNG, разрешение не менее 300 dpi)\n"
            "2. Актуальный адрес электронной почты заявителя\n\n"
            "Просим Вас предоставить указанные документы и сведения в течение 5 рабочих дней.\n\n"
            "С уважением,\nПатентное бюро"
        ),
        "missing_items": [
            {"item": "Изображение товарного знака", "deadline_days": 5},
            {"item": "Email заявителя", "deadline_days": 5},
        ],
        "urgency": "normal",
        "language": "ru",
    },
    "status_notification": {
        "subject": "Изменение статуса Вашей заявки",
        "body": (
            "Уважаемый Клиент,\n\n"
            "Сообщаем Вам, что статус Вашей заявки на регистрацию товарного знака "
            "изменился.\n\n"
            "Новый статус: На рассмотрении в Роспатенте\n"
            "Дата изменения: {status_date}\n\n"
            "С уважением,\nПатентное бюро"
        ),
        "status_code": "examination",
        "status_label_ru": "На рассмотрении в Роспатенте",
        "requires_action": False,
        "next_expected_status": "registered",
        "estimated_days": 30,
        "language": "ru",
    },
}


def _build_rag_analysis_response(full_text: str) -> str | None:
    """Ответ для RAG-анализа абсолютных оснований.

    Промпт содержит раздел ИСТОЧНИКИ с блоками вида
    ``[source_id: kb-N] [название — якорь]`` и текстом фрагмента.
    Заготовленная цитата здесь не годится: она не пройдёт проверку,
    потому что её нет в базе знаний. Поэтому mock берёт настоящий
    фрагмент из переданного контекста — так демонстрируется весь
    контур целиком, включая подтверждение цитаты.
    """
    blocks = re.findall(
        r"\[source_id:\s*(kb-\d+)\]\s*\[([^\]]*)\]\s*\n(.+?)(?=\n\n---\n\n|\Z)",
        full_text,
        re.DOTALL,
    )
    if not blocks:
        return None

    source_id, header, content = blocks[0]
    anchor = header.split("—")[-1].strip() if "—" in header else header.strip()

    # Берём осмысленный отрезок реального текста источника.
    # Первая строка фрагмента — заголовок раздела («Пункт 4. ...»),
    # он слишком короткий и цитатой служить не может.
    body = "\n".join(content.strip().splitlines()[1:]) or content
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", body.strip()) if s.strip()]
    quote = next(
        (s for s in sentences if len(s.split()) >= 6),
        " ".join(body.split())[:200],
    )
    quote = " ".join(quote.split())[:280]

    return json.dumps(
        {
            "overall_risk": "medium",
            "summary": (
                "Демонстрационный анализ: проверка выполнена по нормативным "
                "материалам базы знаний. Требуется оценка специалистом."
            ),
            "findings": [
                {
                    "category": "no_distinctiveness",
                    "level": "medium",
                    "legal_basis": f"ГК РФ {anchor}" if anchor else "ГК РФ ст. 1483",
                    "explanation": (
                        "Обозначение следует проверить на соответствие требованию "
                        "различительной способности применительно к заявленным "
                        "товарам и услугам. Вывод демонстрационный."
                    ),
                    "case_facts_used": ["Заявленное обозначение", "Перечень товаров и услуг"],
                    "citations": [
                        {"source_id": source_id, "quote": quote, "anchor": anchor}
                    ],
                    "confidence": 0.55,
                    "missing_data": [
                        "Сведения об использовании обозначения",
                        "Результаты поиска по реестру товарных знаков",
                    ],
                    "recommended_action": (
                        "Провести проверку по реестру и оценить приобретённую "
                        "различительную способность"
                    ),
                }
            ],
            "limitations": [
                "Ответ сформирован демонстрационным провайдером (LLM_PROVIDER=mock), "
                "а не реальной языковой моделью",
                "Поиск по реестру товарных знаков не выполнялся",
                "База знаний ограничена загруженными материалами",
            ],
            "missing_data": ["Результаты поиска по реестру"],
            "requires_specialist_review": True,
        },
        ensure_ascii=False,
    )


def _detect_topic(messages: list[LLMMessage]) -> str:
    """Detect which topic the messages relate to based on keyword matching."""
    full_text = " ".join(m.content.lower() for m in messages)

    patterns = {
        "intake": ["intake", "completeness", "missing", "полнот", "заявк", "недостающ"],
        "absolute_grounds": ["absolute", "абсолют", "1483", "описательн", "generic", "обманн"],
        "relative_grounds": ["relative", "относительн", "схожест", "similarity", "conflict"],
        "nice_class": ["nice", "мкту", "class", "класс", "nktu", "classification"],
        "conflict_query": ["query", "search query", "запрос", "поиск", "transliterat"],
        "conflict_analysis": ["conflict analysis", "анализ конфликт", "risk level", "уровень риска"],
        "recommendation": ["recommend", "рекоменд", "lawyer", "юрист", "memo"],
        "document_mapping": ["document", "mapping", "докумен", "шаблон", "template", "поле"],
        "client_notification": ["client", "клиент", "missing data", "недостающ", "запрос данных"],
        "status_notification": ["status", "статус", "изменение", "change", "уведомлен"],
    }

    scores: dict[str, int] = {k: 0 for k in patterns}
    for topic, keywords in patterns.items():
        for kw in keywords:
            if kw in full_text:
                scores[topic] += 1

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "recommendation"


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM provider that returns deterministic, realistic responses for
    trademark analysis workflows. Useful for testing and offline development.
    """

    MODEL_NAME = "mock-gpt-4o"

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        t0 = time.time()
        full_text = " ".join(m.content for m in messages)

        # RAG-анализ распознаётся по разделу ИСТОЧНИКИ в промпте:
        # для него нужен ответ в схеме AnalysisResult с настоящей цитатой.
        content = _build_rag_analysis_response(full_text)
        if content is None:
            topic = _detect_topic(messages)
            structured = _CANNED_STRUCTURED.get(topic, _CANNED_STRUCTURED["recommendation"])
            content = json.dumps(structured, ensure_ascii=False, indent=2)
        latency = int((time.time() - t0) * 1000) + 42  # simulate small latency
        return LLMResponse(
            content=content,
            model=self.MODEL_NAME,
            tokens_input=sum(len(m.content.split()) for m in messages),
            tokens_output=len(content.split()),
            latency_ms=latency,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        topic = _detect_topic(messages)
        return _CANNED_STRUCTURED.get(topic, _CANNED_STRUCTURED["recommendation"])
