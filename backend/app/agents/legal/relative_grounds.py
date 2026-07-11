"""
RelativeGroundsAgent — analyses relative grounds for refusal under Art.1483 ГК РФ.
Uses conflict records returned by ConflictSearchOrchestrator.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)


class RelativeGroundsAgent(BaseAgent):
    """
    Analyses relative grounds for refusal (п.6-9 ст.1483 ГК РФ).
    Performs visual, phonetic and semantic similarity assessment
    against a set of conflicting registry records.

    Input dict keys:
        applicant_mark (dict): {text, type, classes, goods_services_description}
        conflicting_marks (list): list of RegistryRecord-like dicts
        analysis_depth (str): 'quick' | 'standard' | 'deep'

    Output findings: LLM-structured analysis (see relative_grounds_review prompt)
    """

    agent_type = "legal.relative_grounds"

    input_schema = {
        "type": "object",
        "required": ["applicant_mark", "conflicting_marks"],
        "properties": {
            "applicant_mark": {"type": "object"},
            "conflicting_marks": {"type": "array"},
            "analysis_depth": {
                "type": "string",
                "enum": ["quick", "standard", "deep"],
                "default": "standard",
            },
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        applicant_mark = input_data.get("applicant_mark", {})
        conflicting_marks = input_data.get("conflicting_marks", [])
        analysis_depth = input_data.get("analysis_depth", "standard")

        if not conflicting_marks:
            return StructuredAgentOutput(
                summary="Конфликтующих обозначений не найдено. Относительные основания не выявлены.",
                findings={
                    "has_relative_grounds": False,
                    "conflicts_found": [],
                    "overall_risk": "low",
                    "recommendation": "Продолжить подготовку к подаче",
                    "confidence": 0.95,
                },
                confidence=0.95,
                next_actions=["proceed_to_recommendation"],
            )

        variables = {
            "applicant_mark": applicant_mark,
            "conflicting_marks": conflicting_marks,
            "analysis_depth": analysis_depth,
        }

        try:
            llm_result = await self._call_llm_structured(
                "legal.relative_grounds_review", variables
            )
        except Exception as exc:
            logger.error("RelativeGroundsAgent LLM call failed: %s", exc)
            llm_result = {
                "has_relative_grounds": len(conflicting_marks) > 0,
                "conflicts_found": [
                    {
                        "conflict_mark": c.get("mark_text", ""),
                        "registration_number": c.get("record_id", ""),
                        "classes": c.get("classes", []),
                        "similarity_type": ["visual"],
                        "similarity_score": 0.5,
                        "owner": c.get("owner", ""),
                        "risk": "medium",
                    }
                    for c in conflicting_marks[:3]
                ],
                "overall_risk": "medium",
                "recommendation": "Требуется ручной анализ (LLM недоступен)",
                "confidence": 0.4,
            }

        risk_level = llm_result.get("overall_risk", "low")
        human_review = risk_level in ("high", "critical")

        # Build evidence list
        evidence = [
            {
                "source": "conflict_registry",
                "record_id": c.get("conflict_mark", c.get("record_id", "")),
                "risk": c.get("risk", ""),
            }
            for c in llm_result.get("conflicts_found", [])
        ]

        summary = (
            f"Относительные основания: "
            f"{'найдены конфликты' if llm_result.get('has_relative_grounds') else 'не выявлены'}. "
            f"Конфликтов: {len(llm_result.get('conflicts_found', []))}. "
            f"Общий риск: {risk_level}."
        )

        next_actions: list[str] = []
        if not llm_result.get("has_relative_grounds"):
            next_actions.append("proceed_to_recommendation")
        elif risk_level == "critical":
            next_actions.extend(["human_review_required", "notify_client_critical_conflict"])
        elif risk_level == "high":
            next_actions.extend(["human_review_required", "consider_mark_modification"])
        else:
            next_actions.append("proceed_to_recommendation_with_caveats")

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            evidence=evidence,
            confidence=llm_result.get("confidence", 0.8),
            human_review_required=human_review,
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
