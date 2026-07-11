"""
ConflictAnalysisAgent — analyses found conflicts, assesses risk level,
and recommends action.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

_RISK_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class ConflictAnalysisAgent(BaseAgent):
    """
    Analyses conflicts returned by the ConflictSearchOrchestrator.

    Input dict keys:
        applicant_mark (dict): {text, type, classes, goods_services_description}
        conflicts (list): RegistryRecord-like dicts with optional similarity scores
        applicant_budget (str, optional): 'low'|'medium'|'high'

    Output findings: LLM-structured analysis (see conflict_analysis prompt)
    """

    agent_type = "conflicts.analyzer"

    input_schema = {
        "type": "object",
        "required": ["applicant_mark", "conflicts"],
        "properties": {
            "applicant_mark": {"type": "object"},
            "conflicts": {"type": "array"},
            "applicant_budget": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        applicant_mark = input_data.get("applicant_mark", {})
        conflicts = input_data.get("conflicts", [])

        if not conflicts:
            return StructuredAgentOutput(
                summary="Конфликты для анализа отсутствуют.",
                findings={
                    "total_conflicts": 0,
                    "high_risk_conflicts": 0,
                    "medium_risk_conflicts": 0,
                    "low_risk_conflicts": 0,
                    "critical_conflicts": 0,
                    "overall_risk": "low",
                    "detailed_analysis": [],
                    "recommended_action": "proceed",
                    "confidence": 0.99,
                },
                confidence=0.99,
                next_actions=["proceed_to_recommendation"],
            )

        variables: dict = {
            "applicant_mark": applicant_mark,
            "conflicts": conflicts,
        }
        if "applicant_budget" in input_data:
            variables["applicant_budget"] = input_data["applicant_budget"]

        try:
            llm_result = await self._call_llm_structured(
                "conflicts.conflict_analysis", variables
            )
        except Exception as exc:
            logger.error("ConflictAnalysisAgent LLM call failed: %s", exc)
            llm_result = {
                "total_conflicts": len(conflicts),
                "high_risk_conflicts": 0,
                "medium_risk_conflicts": len(conflicts),
                "low_risk_conflicts": 0,
                "critical_conflicts": 0,
                "overall_risk": "medium",
                "detailed_analysis": [],
                "recommended_action": "human_review",
                "action_rationale": "LLM недоступен — передать на ручной анализ",
                "confidence": 0.3,
            }

        overall_risk = llm_result.get("overall_risk", "low")
        human_review = overall_risk in ("high", "critical")
        recommended_action = llm_result.get("recommended_action", "human_review")

        summary = (
            f"Анализ конфликтов: итого {llm_result.get('total_conflicts', 0)}, "
            f"критических {llm_result.get('critical_conflicts', 0)}, "
            f"высокого риска {llm_result.get('high_risk_conflicts', 0)}. "
            f"Общий риск: {overall_risk}. "
            f"Рекомендация: {recommended_action}."
        )

        # Build evidence from detailed analysis
        evidence = [
            {
                "record_id": item.get("record_id"),
                "mark": item.get("mark"),
                "risk": item.get("risk_level"),
                "likelihood_of_confusion": item.get("likelihood_of_confusion"),
            }
            for item in llm_result.get("detailed_analysis", [])
        ]

        next_actions: list[str] = []
        action_map = {
            "proceed": ["proceed_to_recommendation"],
            "modify_mark": ["request_mark_modification_from_client", "human_review_required"],
            "modify_goods_services": ["request_goods_modification", "human_review_required"],
            "file_coexistence": ["prepare_coexistence_request", "human_review_required"],
            "challenge_prior": ["prepare_challenge_materials", "human_review_required"],
            "human_review": ["human_review_required"],
            "abandon": ["notify_client_registration_impractical", "human_review_required"],
        }
        next_actions = action_map.get(recommended_action, ["human_review_required"])

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            evidence=evidence,
            confidence=llm_result.get("confidence", 0.8),
            human_review_required=human_review,
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
