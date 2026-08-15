"""Controlled LLM review of shortlisted trademark registry records.

The registry remains the source of facts and deterministic similarity remains
the source of numeric scores.  The model receives a bounded, structured copy
of the shortlisted records only to explain confusion factors and suggest what
a specialist should inspect next.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.infrastructure.llm.base import LLMMessage
from app.infrastructure.llm.prompt_registry import PromptDefinition, PromptRegistry

logger = get_logger(__name__)

PROMPT_ID = "legal.registry_conflict_review"
MAX_REGISTRY_RECORDS_FOR_LLM = 10

_LEGAL_METHODOLOGY = {
    "sources": [
        {
            "id": "rules_482_40_45",
            "title": "Правила, утверждённые приказом Минэкономразвития России от 20.07.2015 № 482 (ред. от 01.03.2023)",
            "anchors": ["пункты 40–45"],
            "url": "https://rospatent.gov.ru/ru/documents/482-prikaz-minekonomrazvitiya-rossii-ot-20-07-2015-482",
        },
        {
            "id": "plenum_10_162",
            "title": "Постановление Пленума Верховного Суда РФ от 23.04.2019 № 10",
            "anchors": ["пункт 162"],
            "url": "https://www.vsrf.ru/files/27771/",
        },
        {
            "id": "fips_trademark_guide",
            "title": "Руководство ФИПС по экспертизе заявок на товарные знаки",
            "anchors": ["оценка сходства", "однородность товаров и услуг"],
            "url": "https://rospatent.gov.ru/ru/documents/rucov-po",
        },
    ],
    "mandatory_sequence": [
        "Проверить вид записи, статус и более ранний приоритет; при нехватке дат не делать категоричный вывод.",
        "Сопоставить не номера классов сами по себе, а товары и услуги: назначение, свойства, взаимодополняемость или взаимозаменяемость, каналы реализации и круг потребителей.",
        "Определить тождество либо ассоциацию обозначений в целом, несмотря на отдельные отличия.",
        "Для словесных элементов отдельно проверить звуковое, графическое и смысловое сходство; для комбинированных — доминирующие и сильные элементы и их положение.",
        "Не придавать самостоятельного решающего значения совпадению только слабых, описательных или неохраняемых элементов.",
        "Оценить взаимное влияние степени сходства обозначений и однородности товаров на вероятность смешения у обычного потребителя.",
        "Сформулировать аргументы за риск, контраргументы, недостающие доказательства и практическое действие юриста.",
    ],
}


@dataclass(frozen=True)
class RegistryContextReview:
    """Sanitised model output linked only to submitted registry record IDs."""

    summary: str
    overall_observation: str
    confidence: float | None
    comments: dict[str, dict[str, Any]]
    overall_risk: str = "uncertain"
    methodology_steps: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "overall_observation": self.overall_observation,
            "confidence": self.confidence,
            "overall_risk": self.overall_risk,
            "methodology_steps": list(self.methodology_steps),
            "record_reviews": [
                {"record_id": record_id, **comment}
                for record_id, comment in self.comments.items()
            ],
        }


@lru_cache(maxsize=1)
def _prompt_registry() -> PromptRegistry:
    registry = PromptRegistry()
    prompts_dir = Path(__file__).resolve().parents[3] / "prompts"
    registry.load_from_directory(prompts_dir)
    if registry.get(PROMPT_ID) is None:
        raise RuntimeError(f"Prompt {PROMPT_ID!r} is not loaded")
    return registry


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _record_payload(record: Any, similarity: Any) -> dict[str, Any]:
    return {
        "record_id": _bounded_text(record.record_id, 300),
        "source": _bounded_text(record.source, 30),
        "external_id": _bounded_text(record.external_id, 200),
        "mark_text": _bounded_text(record.mark_text, 500),
        "mark_type": _bounded_text(record.mark_type, 50),
        "owner": _bounded_text(record.owner, 500),
        "classes": list(record.classes or [])[:45],
        "status": _bounded_text(record.status, 50),
        "filing_date": record.filing_date,
        "registration_date": record.registration_date,
        "application_number": record.application_number,
        "registration_number": record.registration_number,
        "image_available": bool(record.image_url),
        "similarity": similarity.as_dict(),
    }


def _confidence(value: Any) -> float | None:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return None


def _risk(value: Any) -> str:
    risk = _bounded_text(value, 20).casefold()
    return risk if risk in {"low", "medium", "high", "critical", "uncertain"} else "uncertain"


def _strings(value: Any, *, count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = [_bounded_text(item, limit) for item in value[:count]]
    return [item for item in result if item]


async def review_registry_context(
    llm_provider: Any,
    *,
    applicant_mark: str,
    applicant_mark_type: str | None,
    applicant_classes: list[int],
    applicant_goods: str,
    conflicts: list[tuple[Any, Any]],
    provider_name: str,
    search_mode: str,
    class_context_description: str = "не определены",
    classes_confirmed: bool = False,
    applicant_details: dict[str, Any] | None = None,
) -> RegistryContextReview | None:
    """Send a bounded shortlist of real registry facts to the configured LLM.

    Model output is advisory. Unknown record IDs and oversized free text are
    discarded so that a hallucinated card cannot enter the audit trail.
    """
    if llm_provider is None or not conflicts:
        return None
    generate_structured = getattr(llm_provider, "generate_structured", None)
    if not callable(generate_structured):
        return None

    shortlisted = conflicts[:MAX_REGISTRY_RECORDS_FOR_LLM]
    records = [
        _record_payload(record, similarity) for record, similarity in shortlisted
    ]
    allowed_ids = {item["record_id"] for item in records}
    applicant = {
        "mark_text": _bounded_text(applicant_mark, 500),
        "mark_type": _bounded_text(applicant_mark_type, 50),
        "classes": list(applicant_classes)[:45],
        "goods_services": _bounded_text(applicant_goods, 3000),
        "class_context": _bounded_text(class_context_description, 3000),
        "classes_confirmed_by_specialist": bool(classes_confirmed),
        "additional_mark_data": {
            _bounded_text(key, 80): _bounded_text(value, 1000)
            for key, value in (applicant_details or {}).items()
            if value not in (None, "")
        },
    }
    context = {
        "provider": _bounded_text(provider_name, 100),
        "search_mode": _bounded_text(search_mode, 30),
        "records_sent": len(records),
        "class_first_search": bool(applicant_classes),
    }

    try:
        registry = _prompt_registry()
        definition: PromptDefinition | None = registry.get(PROMPT_ID)
        if definition is None:  # guarded when the cached registry is created
            raise RuntimeError(f"Prompt {PROMPT_ID!r} is not loaded")
        user_prompt = registry.render(
            PROMPT_ID,
            {
                "applicant_json": json.dumps(applicant, ensure_ascii=False, indent=2),
                "registry_context_json": json.dumps(
                    context, ensure_ascii=False, indent=2
                ),
                "records_json": json.dumps(records, ensure_ascii=False, indent=2),
                "legal_methodology_json": json.dumps(
                    _LEGAL_METHODOLOGY, ensure_ascii=False, indent=2
                ),
            },
        )
        result = await generate_structured(
            messages=[
                LLMMessage(role="system", content=definition.system),
                LLMMessage(role="user", content=user_prompt),
            ],
            output_schema=definition.output_schema,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM registry context review failed", error=str(exc))
        return None
    if not isinstance(result, dict):
        logger.warning("LLM registry context review returned a non-object")
        return None

    summary = _bounded_text(result.get("summary"), 1500)
    overall_observation = _bounded_text(
        result.get("overall_observation"), 1500
    )
    if not summary and not overall_observation and "record_reviews" not in result:
        logger.warning("LLM registry context review did not match the expected schema")
        return None

    comments: dict[str, dict[str, Any]] = {}
    raw_reviews = result.get("record_reviews") or []
    if isinstance(raw_reviews, list):
        for item in raw_reviews:
            if not isinstance(item, dict):
                continue
            record_id = _bounded_text(item.get("record_id"), 300)
            if record_id not in allowed_ids or record_id in comments:
                continue
            factors = _strings(item.get("confusion_factors"), count=8, limit=400)
            risk = _risk(item.get("legal_risk"))
            attention = item.get("requires_attention") is True
            comments[record_id] = {
                "comment": _bounded_text(item.get("comment"), 1000),
                "legal_risk": risk,
                "requires_attention": attention,
                "mark_similarity_analysis": _bounded_text(
                    item.get("mark_similarity_analysis"), 1200
                ),
                "goods_homogeneity_analysis": _bounded_text(
                    item.get("goods_homogeneity_analysis"), 1200
                ),
                "priority_and_status_analysis": _bounded_text(
                    item.get("priority_and_status_analysis"), 800
                ),
                "confusion_factors": factors,
                "counterarguments": _strings(
                    item.get("counterarguments"), count=6, limit=400
                ),
                "missing_evidence": _strings(
                    item.get("missing_evidence"), count=6, limit=400
                ),
                "legal_references": _strings(
                    item.get("legal_references"), count=6, limit=200
                ),
                "recommended_action": _bounded_text(
                    item.get("recommended_action"), 500
                ),
            }

    return RegistryContextReview(
        summary=summary,
        overall_observation=overall_observation,
        confidence=_confidence(result.get("confidence")),
        comments=comments,
        overall_risk=_risk(result.get("overall_risk")),
        methodology_steps=tuple(
            _strings(result.get("methodology_steps"), count=10, limit=500)
        ),
    )
