"""
NiceClassificationAgent — suggests MKTU (Nice Classification) classes
based on business description and goods/services.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

# Minimum acceptable confidence for auto-acceptance
_AUTO_ACCEPT_CONFIDENCE = 0.85


class NiceClassificationAgent(BaseAgent):
    """
    Suggests MKTU classes for a trademark application.

    Input dict keys:
        business_description (str)
        goods_services (list[str])
        existing_classes (list[int], optional)
        target_market (str, optional)
        budget_constraint (bool, optional)

    Output findings:
        primary_classes, secondary_classes, borderline_classes,
        recommended_class_description, total_classes, confidence
    """

    agent_type = "classification.nice_classifier"

    input_schema = {
        "type": "object",
        "required": ["business_description", "goods_services"],
        "properties": {
            "business_description": {"type": "string"},
            "goods_services": {"type": "array", "items": {"type": "string"}},
            "existing_classes": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "target_market": {"type": "string"},
            "budget_constraint": {"type": "boolean", "default": False},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        variables = {
            "business_description": input_data.get("business_description", ""),
            "goods_services": input_data.get("goods_services", []),
        }
        if "existing_classes" in input_data:
            variables["existing_classes"] = input_data["existing_classes"]
        if "target_market" in input_data:
            variables["target_market"] = input_data["target_market"]
        if "budget_constraint" in input_data:
            variables["budget_constraint"] = input_data["budget_constraint"]

        try:
            llm_result = await self._call_llm_structured(
                "classes.nice_class_suggestion", variables
            )
        except Exception as exc:
            logger.error("NiceClassificationAgent LLM call failed: %s", exc)
            return StructuredAgentOutput(
                summary="Классификация МКТУ: LLM недоступен. Требуется ручное определение классов.",
                findings={"error": str(exc)},
                confidence=0.0,
                human_review_required=True,
                error=str(exc),
            )

        confidence = llm_result.get("confidence", 0.0)
        primary = llm_result.get("primary_classes", [])
        secondary = llm_result.get("secondary_classes", [])
        borderline = llm_result.get("borderline_classes", [])
        total = llm_result.get("total_classes", len(primary) + len(secondary))

        all_classes = [c["class"] for c in primary] + [c["class"] for c in secondary]

        summary = (
            f"Классификация МКТУ: основных классов {len(primary)}, "
            f"дополнительных {len(secondary)}, пограничных {len(borderline)}. "
            f"Итого: {total} класс(ов). "
            f"Уверенность: {confidence:.0%}."
        )

        next_actions: list[str] = []
        if confidence >= _AUTO_ACCEPT_CONFIDENCE:
            next_actions.append("apply_classes_to_application")
        else:
            next_actions.append("human_review_classification")

        if borderline:
            next_actions.append("clarify_borderline_classes_with_client")

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            confidence=confidence,
            evidence=[{"suggested_classes": all_classes}],
            human_review_required=confidence < _AUTO_ACCEPT_CONFIDENCE,
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
