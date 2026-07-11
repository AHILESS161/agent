"""
HumanReviewPacketAgent — assembles a complete review packet for the lawyer,
collecting all agent outputs into a single structured document.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}


class HumanReviewPacketAgent(BaseAgent):
    """
    Prepares a human review packet by aggregating all agent outputs.
    Assigns priority, lists open questions, and structures the packet
    for the reviewing lawyer.

    Input dict keys:
        application_id (str)
        mark_text (str)
        applicant_name (str)
        agent_outputs (dict): {agent_type: StructuredAgentOutput.to_dict()}
        review_reason (str): why human review was triggered
        deadline_date (str, optional)

    Output findings:
        review_packet (structured dict for lawyer UI)
    """

    agent_type = "human_review.packager"

    input_schema = {
        "type": "object",
        "required": ["application_id", "mark_text", "applicant_name", "agent_outputs", "review_reason"],
        "properties": {
            "application_id": {"type": "string"},
            "mark_text": {"type": "string"},
            "applicant_name": {"type": "string"},
            "agent_outputs": {"type": "object"},
            "review_reason": {"type": "string"},
            "deadline_date": {"type": "string"},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        application_id = input_data.get("application_id", "")
        mark_text = input_data.get("mark_text", "")
        applicant_name = input_data.get("applicant_name", "")
        agent_outputs = input_data.get("agent_outputs", {})
        review_reason = input_data.get("review_reason", "")
        deadline_date = input_data.get("deadline_date")

        # Determine overall risk across all agent outputs
        overall_risk = "low"
        all_missing_info: list[dict] = []
        all_next_actions: list[str] = []
        sections: list[dict] = []

        for agent_type, output_dict in agent_outputs.items():
            findings = output_dict.get("findings", {})
            risk = (
                findings.get("risk_level")
                or findings.get("overall_risk")
                or findings.get("risk_assessment", {}).get("overall_risk")
                or "low"
            )

            if _PRIORITY_MAP.get(risk, 9) < _PRIORITY_MAP.get(overall_risk, 9):
                overall_risk = risk

            all_missing_info.extend(output_dict.get("missing_info", []))
            all_next_actions.extend(output_dict.get("next_actions", []))

            sections.append(
                {
                    "section": agent_type,
                    "summary": output_dict.get("summary", ""),
                    "risk": risk,
                    "confidence": output_dict.get("confidence", 0.0),
                    "human_review_required": output_dict.get("human_review_required", False),
                    "key_findings": _extract_key_findings(agent_type, findings),
                }
            )

        # Sort sections by risk priority
        sections.sort(key=lambda s: _PRIORITY_MAP.get(s["risk"], 9))

        # Deduplicate next actions
        unique_next_actions = list(dict.fromkeys(all_next_actions))

        review_packet = {
            "application_id": application_id,
            "mark_text": mark_text,
            "applicant_name": applicant_name,
            "review_reason": review_reason,
            "overall_risk": overall_risk,
            "priority": _PRIORITY_MAP.get(overall_risk, 4),
            "created_at": datetime.utcnow().isoformat(),
            "deadline_date": deadline_date,
            "sections": sections,
            "all_missing_info": all_missing_info,
            "recommended_actions": unique_next_actions,
            "total_sections": len(sections),
        }

        summary = (
            f"Пакет для проверки юристом собран: «{mark_text}» ({applicant_name}). "
            f"Причина: {review_reason}. "
            f"Риск: {overall_risk}. "
            f"Разделов: {len(sections)}."
        )

        return StructuredAgentOutput(
            summary=summary,
            findings={"review_packet": review_packet},
            missing_info=all_missing_info,
            confidence=0.99,
            human_review_required=True,
            next_actions=["assign_to_lawyer", "notify_lawyer"],
        )


def _extract_key_findings(agent_type: str, findings: dict) -> list[str]:
    """Extract top 3 key finding strings from an agent's findings dict."""
    results: list[str] = []

    if agent_type == "intake.validator":
        score = findings.get("completeness_score", 0)
        results.append(f"Полнота заявки: {score:.0%}")
        for gap in findings.get("missing_fields", [])[:2]:
            results.append(f"Отсутствует: {gap.get('field', '')} ({gap.get('criticality', '')})")

    elif agent_type == "legal.absolute_grounds":
        results.append(
            f"Абсолютные основания: {'есть' if findings.get('has_absolute_grounds') else 'нет'}"
        )
        for g in findings.get("grounds_found", [])[:2]:
            results.append(f"{g.get('article_point', '')}: {g.get('description', '')[:80]}")

    elif agent_type == "legal.relative_grounds":
        n = len(findings.get("conflicts_found", []))
        results.append(f"Конфликтующих обозначений: {n}")
        for c in findings.get("conflicts_found", [])[:2]:
            results.append(f"{c.get('conflict_mark', '')} — риск: {c.get('risk', '')}")

    elif agent_type == "conflicts.analyzer":
        results.append(f"Всего конфликтов: {findings.get('total_conflicts', 0)}")
        results.append(f"Рекомендованное действие: {findings.get('recommended_action', '')}")

    elif agent_type == "recommendations.recommender":
        results.extend(findings.get("key_findings", [])[:3])

    else:
        # Generic: take summary
        summary = findings.get("summary") or findings.get("recommendation", "")
        if summary:
            results.append(summary[:120])

    return results[:3]
