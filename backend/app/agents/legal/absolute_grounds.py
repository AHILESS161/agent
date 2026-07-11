"""
AbsoluteGroundsAgent — analyses absolute grounds for refusal under Art.1483 ГК РФ.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

# Quick pre-screen: descriptive suffixes/prefixes common in Russian
_GENERIC_PATTERNS = [
    "СЕРВИС", "УСЛУГИ", "МАГАЗИН", "ОНЛАЙН", "ЦЕНТР", "ГРУПП",
    "ХОЛДИНГ", "СИСТЕМЫ", "РЕШЕНИЯ", "ТЕХНОЛОГИИ", "ПРОДУКТ",
]


def _pre_screen_descriptive(mark_text: str) -> list[str]:
    """Return any generic/descriptive pattern hits found in the mark text."""
    upper = mark_text.upper()
    return [p for p in _GENERIC_PATTERNS if p in upper]


class AbsoluteGroundsAgent(BaseAgent):
    """
    Analyses absolute grounds for refusal (ст.1483 ГК РФ п.1-4).

    Input dict keys:
        mark_text (str)
        mark_type (str)
        classes_with_description (list[{class, description}])
        applicant_name (str, optional)
        prior_use_evidence (str, optional)

    Output findings: LLM-structured analysis (see prompt output_schema)
    """

    agent_type = "legal.absolute_grounds"

    input_schema = {
        "type": "object",
        "required": ["mark_text", "mark_type", "classes_with_description"],
        "properties": {
            "mark_text": {"type": "string"},
            "mark_type": {"type": "string"},
            "classes_with_description": {
                "type": "array",
                "items": {"type": "object"},
            },
            "applicant_name": {"type": "string"},
            "prior_use_evidence": {"type": "string"},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        mark_text = input_data.get("mark_text", "")
        mark_type = input_data.get("mark_type", "словесное")
        classes_info = input_data.get("classes_with_description", [])
        applicant_name = input_data.get("applicant_name")
        prior_use_evidence = input_data.get("prior_use_evidence")

        # Local pre-screen
        pre_screen_hits = _pre_screen_descriptive(mark_text)

        # Build LLM prompt variables
        variables: dict = {
            "mark_text": mark_text,
            "mark_type": mark_type,
            "classes_with_description": classes_info,
        }
        if applicant_name:
            variables["applicant_name"] = applicant_name
        if prior_use_evidence:
            variables["prior_use_evidence"] = prior_use_evidence

        try:
            llm_result = await self._call_llm_structured(
                "legal.absolute_grounds_review", variables
            )
        except Exception as exc:
            logger.error("AbsoluteGroundsAgent LLM call failed: %s", exc)
            # Fallback: use pre-screen results only
            llm_result = {
                "has_absolute_grounds": len(pre_screen_hits) > 0,
                "grounds_found": [
                    {
                        "article_point": "подп.3 п.1 ст.1483 ГК РФ",
                        "ground_type": "descriptive",
                        "description": f"Обозначение содержит описательный элемент: {hit}",
                        "severity": "significant",
                    }
                    for hit in pre_screen_hits
                ],
                "risk_level": "medium" if pre_screen_hits else "low",
                "analysis": "Автоматическая предварительная проверка (LLM недоступен)",
                "articles_triggered": ["п.1 ст.1483 ГК РФ"] if pre_screen_hits else [],
                "recommendation": "Требуется ручная проверка",
                "confidence": 0.5,
            }

        # Determine if human review needed
        risk_level = llm_result.get("risk_level", "low")
        human_review = risk_level in ("high", "critical")

        findings = {
            **llm_result,
            "pre_screen_hits": pre_screen_hits,
        }

        summary = (
            f"Абсолютные основания (ст.1483 ГК РФ): "
            f"{'выявлены' if llm_result.get('has_absolute_grounds') else 'не выявлены'}. "
            f"Уровень риска: {risk_level}. "
            f"Уверенность: {llm_result.get('confidence', 0):.0%}."
        )

        next_actions: list[str] = []
        if not llm_result.get("has_absolute_grounds"):
            next_actions.append("proceed_to_relative_grounds_check")
        else:
            if risk_level in ("high", "critical"):
                next_actions.append("human_review_required")
            next_actions.append("notify_client_of_absolute_grounds_risk")

        return StructuredAgentOutput(
            summary=summary,
            findings=findings,
            confidence=llm_result.get("confidence", 0.8),
            human_review_required=human_review,
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
