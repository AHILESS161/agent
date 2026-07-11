"""
RecommendationAgent — generates a comprehensive recommendation memo
for lawyer review, aggregating all prior analysis results.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)


class RecommendationAgent(BaseAgent):
    """
    Generates the final lawyer recommendation memo.

    Input dict keys:
        application_id (str)
        mark_text (str)
        mark_type (str)
        classes (list[int])
        applicant_name (str)
        intake_result (dict): output from IntakeValidatorAgent
        absolute_grounds_result (dict): output from AbsoluteGroundsAgent
        relative_grounds_result (dict): output from RelativeGroundsAgent
        classification_result (dict): output from NiceClassificationAgent
        created_at (str, optional)
        additional_context (str, optional)

    Output findings: LLM-structured recommendation memo
    """

    agent_type = "recommendations.recommender"

    input_schema = {
        "type": "object",
        "required": [
            "application_id",
            "mark_text",
            "mark_type",
            "classes",
            "applicant_name",
            "intake_result",
            "absolute_grounds_result",
            "relative_grounds_result",
            "classification_result",
        ],
        "properties": {
            "application_id": {"type": "string"},
            "mark_text": {"type": "string"},
            "mark_type": {"type": "string"},
            "classes": {"type": "array", "items": {"type": "integer"}},
            "applicant_name": {"type": "string"},
            "intake_result": {"type": "object"},
            "absolute_grounds_result": {"type": "object"},
            "relative_grounds_result": {"type": "object"},
            "classification_result": {"type": "object"},
            "created_at": {"type": "string"},
            "additional_context": {"type": "string"},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        variables = {
            "application_id": input_data.get("application_id", ""),
            "mark_text": input_data.get("mark_text", ""),
            "mark_type": input_data.get("mark_type", "словесное"),
            "classes": input_data.get("classes", []),
            "applicant_name": input_data.get("applicant_name", ""),
            "intake_result": input_data.get("intake_result", {}),
            "absolute_grounds_result": input_data.get("absolute_grounds_result", {}),
            "relative_grounds_result": input_data.get("relative_grounds_result", {}),
            "classification_result": input_data.get("classification_result", {}),
            "created_at": input_data.get("created_at", datetime.utcnow().date().isoformat()),
        }
        if "additional_context" in input_data:
            variables["additional_context"] = input_data["additional_context"]

        try:
            llm_result = await self._call_llm_structured(
                "recommendations.lawyer_recommendation", variables
            )
        except Exception as exc:
            logger.error("RecommendationAgent LLM call failed: %s", exc)
            llm_result = {
                "memo_type": "lawyer_review",
                "summary": "Не удалось сгенерировать рекомендацию (LLM недоступен). Требуется ручной анализ.",
                "key_findings": [],
                "risk_assessment": {
                    "absolute_grounds_risk": "unknown",
                    "relative_grounds_risk": "unknown",
                    "overall_risk": "unknown",
                },
                "recommended_actions": [
                    {
                        "priority": 1,
                        "action": "Ручная проверка всех аспектов заявки",
                        "responsible": "lawyer",
                    }
                ],
                "proceed_to_filing": False,
                "confidence": 0.0,
            }

        overall_risk = llm_result.get("risk_assessment", {}).get("overall_risk", "medium")
        proceed = llm_result.get("proceed_to_filing", False)
        confidence = llm_result.get("confidence", 0.8)

        summary = (
            f"Рекомендация: "
            f"{'✔ подавать' if proceed else '⚠ доработать перед подачей'}. "
            f"Общий риск: {overall_risk}. "
            f"Уверенность: {confidence:.0%}."
        )

        next_actions: list[str] = []
        if proceed:
            next_actions.append("proceed_to_document_assembly")
        else:
            next_actions.append("human_review_required")
            next_actions.append("address_recommended_actions_before_filing")

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            confidence=confidence,
            human_review_required=True,  # Always route through lawyer for recommendations
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
