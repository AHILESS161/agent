from __future__ import annotations

import pytest

from app.agents.classification.rag_class_analyzer import RagNiceClassAnalyzer
from app.infrastructure.rag.store import StoredChunk


class StructuredProvider:
    def __init__(self) -> None:
        self.schema: dict | None = None

    async def generate_structured(
        self, messages, output_schema: dict, temperature: float = 0.1
    ) -> dict:
        self.schema = output_schema
        return {
            "suggestions": [
                {
                    "class_number": 37,
                    "rationale": "Ремонт техники относится к услугам ремонта.",
                    "category": "primary",
                    "goods_services": ["ремонт телефонов"],
                    "confidence": 0.95,
                    "citations": [
                        {
                            "source_id": "kb-1",
                            "quote": "монтаж и ремонт технического оборудования",
                            "anchor": "Класс 37",
                        }
                    ],
                }
            ],
            "summary": "Основной класс — 37 для услуг ремонта техники.",
            "unclassified": [],
            "limitations": ["Результат требует проверки специалистом."],
            "requires_specialist_review": True,
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_class_analyzer_uses_provider_json_schema() -> None:
    chunk = StoredChunk(
        chunk_id=1,
        source_id=1,
        source_name="МКТУ",
        source_version="1",
        source_type="methodology",
        content="Класс 37. Строительство; монтаж и ремонт технического оборудования.",
        anchor="Класс 37. Строительство и ремонт",
        article=None,
        clause=None,
    )
    provider = StructuredProvider()
    analyzer = RagNiceClassAnalyzer(provider, [chunk])

    outcome = await analyzer.analyse(
        {
            "mark_text": "Регистр",
            "business_description": "Ремонт техники",
            "goods_services": "Ремонт телефонов",
        }
    )

    assert outcome.is_conclusive
    assert outcome.result is not None
    assert outcome.result.suggestions[0].class_number == 37
    assert provider.schema is not None
    assert "suggestions" in provider.schema["properties"]
