from __future__ import annotations

from app.agents.legal.registry_context import review_registry_context
from app.document_processing.similarity import assess
from app.infrastructure.providers.base import RegistryRecord


class RecordingStructuredLLM:
    MODEL_NAME = "recording-llm"

    def __init__(self) -> None:
        self.messages = []
        self.schema = None

    async def generate_structured(self, messages, output_schema, temperature=0.1):
        self.messages = messages
        self.schema = output_schema
        return {
            "summary": "Найдены релевантные записи обоих типов.",
            "overall_observation": "Нужна проверка вероятности смешения.",
            "overall_risk": "high",
            "methodology_steps": [
                "Проверены статус и приоритет.",
                "Сопоставлены обозначения и товары.",
            ],
            "record_reviews": [
                {
                    "record_id": "public:registration:1",
                    "legal_risk": "high",
                    "requires_attention": True,
                    "comment": "Совпадает словесный элемент.",
                    "mark_similarity_analysis": "Общее впечатление близкое.",
                    "goods_homogeneity_analysis": "Классы пересекаются.",
                    "priority_and_status_analysis": "Регистрация действует.",
                    "confusion_factors": ["одинаковое обозначение"],
                    "counterarguments": ["Нужно проверить перечень услуг."],
                    "missing_evidence": ["Полный перечень услуг регистрации."],
                    "legal_references": ["п. 41 Правил № 482"],
                    "recommended_action": "Проверить перечни услуг.",
                },
                {
                    "record_id": "invented-by-model",
                    "legal_risk": "critical",
                    "requires_attention": True,
                    "comment": "Этой записи не было во входе.",
                    "mark_similarity_analysis": "",
                    "goods_homogeneity_analysis": "",
                    "priority_and_status_analysis": "",
                    "confusion_factors": [],
                    "counterarguments": [],
                    "missing_evidence": [],
                    "legal_references": [],
                    "recommended_action": "Игнорировать.",
                },
            ],
            "confidence": 0.74,
        }


def _record(**updates) -> RegistryRecord:
    values = {
        "record_id": "public:registration:1",
        "external_id": "uid-1",
        "source": "registration",
        "mark_text": "РЕГИСТР",
        "mark_type": "word",
        "owner": "ООО «Регистр»",
        "classes": [42],
        "status": "registered",
        "filing_date": "2020-01-01",
        "registration_date": "2021-01-01",
        "application_number": "2020123456",
        "registration_number": "998877",
    }
    values.update(updates)
    return RegistryRecord(**values)


async def test_registry_cards_are_sent_to_llm_as_bounded_structured_context():
    llm = RecordingStructuredLLM()
    registration = _record()
    application = _record(
        record_id="public:application:2",
        external_id="uid-2",
        source="application",
        status="pending",
        registration_date=None,
        registration_number=None,
        application_number="2024777000",
    )
    conflicts = [
        (registration, assess("Регистр", registration.mark_text, [42], [42])),
        (application, assess("Регистр", application.mark_text, [42], [42])),
    ]

    review = await review_registry_context(
        llm,
        applicant_mark="Регистр",
        applicant_mark_type="word",
        applicant_classes=[42],
        applicant_goods="разработка программного обеспечения",
        conflicts=conflicts,
        provider_name="rospatent_public",
        search_mode="limited",
    )

    assert review is not None
    prompt = llm.messages[1].content
    assert '"provider": "rospatent_public"' in prompt
    assert '"search_mode": "limited"' in prompt
    assert '"source": "registration"' in prompt
    assert '"registration_number": "998877"' in prompt
    assert '"source": "application"' in prompt
    assert '"application_number": "2024777000"' in prompt
    assert '"owner": "ООО «Регистр»"' in prompt
    assert '"overall":' in prompt
    assert "overall_risk" in llm.schema["required"]
    assert "methodology_steps" in llm.schema["required"]
    assert "record_reviews" in llm.schema["required"]
    assert set(review.comments) == {"public:registration:1"}
    assert review.confidence == 0.74
    assert review.overall_risk == "high"
    assert review.comments["public:registration:1"]["requires_attention"] is True
    assert "№ 482" in prompt
    assert '"class_first_search": true' in prompt


async def test_registry_context_llm_failure_does_not_break_analysis():
    class BrokenLLM:
        async def generate_structured(self, *args, **kwargs):
            raise RuntimeError("temporarily unavailable")

    record = _record()
    review = await review_registry_context(
        BrokenLLM(),
        applicant_mark="Регистр",
        applicant_mark_type="word",
        applicant_classes=[42],
        applicant_goods="",
        conflicts=[(record, assess("Регистр", record.mark_text, [42], [42]))],
        provider_name="rospatent_public",
        search_mode="limited",
    )

    assert review is None
