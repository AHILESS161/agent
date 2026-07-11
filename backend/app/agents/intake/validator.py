"""
IntakeValidatorAgent — checks application completeness, identifies missing
fields, and determines blocking vs non-blocking gaps.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

# Required fields for a complete trademark application
_REQUIRED_FIELDS = [
    "applicant.name",
    "applicant.inn",
    "applicant.ogrn",
    "applicant.address",
    "applicant.email",
    "mark.text",
    "mark.type",
    "classes",
    "goods_services_description",
]

_RECOMMENDED_FIELDS = [
    "applicant.phone",
    "mark.image_file",
    "applicant.representative",
    "priority_date",
]


def _get_nested(data: dict, path: str):
    """Access nested dict by dot-separated path."""
    parts = path.split(".")
    cur = data
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class IntakeValidatorAgent(BaseAgent):
    """
    Validates application completeness on intake.

    Input dict keys:
        application_data (dict): Application fields
        strict (bool): If True, treat recommended fields as non-blocking gaps

    Output findings:
        is_complete, missing_fields, completeness_score,
        blocking_gaps, non_blocking_gaps, recommendation
    """

    agent_type = "intake.validator"

    input_schema = {
        "type": "object",
        "required": ["application_data"],
        "properties": {
            "application_data": {"type": "object"},
            "strict": {"type": "boolean", "default": False},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        app_data = input_data.get("application_data", {})
        strict = input_data.get("strict", False)

        # --- Local structural check ---
        blocking_gaps: list[dict] = []
        non_blocking_gaps: list[dict] = []

        for field_path in _REQUIRED_FIELDS:
            value = _get_nested(app_data, field_path)
            if value is None or value == "" or value == []:
                blocking_gaps.append(
                    {
                        "field": field_path,
                        "reason": f"Обязательное поле «{field_path}» отсутствует",
                        "who_provides": "client",
                        "criticality": "blocking",
                    }
                )

        for field_path in _RECOMMENDED_FIELDS:
            value = _get_nested(app_data, field_path)
            if value is None or value == "":
                criticality = "non_blocking" if not strict else "non_blocking"
                non_blocking_gaps.append(
                    {
                        "field": field_path,
                        "reason": f"Рекомендуемое поле «{field_path}» не заполнено",
                        "who_provides": "client",
                        "criticality": criticality,
                    }
                )

        filled = len(_REQUIRED_FIELDS) - len(blocking_gaps)
        completeness_score = filled / len(_REQUIRED_FIELDS)
        is_complete = len(blocking_gaps) == 0

        # --- LLM enrichment for edge-case analysis ---
        try:
            llm_result = await self._call_llm_structured(
                "intake.missing_info",
                {
                    "application_data": app_data,
                    "required_fields": _REQUIRED_FIELDS,
                    "partial_check": False,
                },
            )
            # Merge LLM analysis with our structural check
            llm_missing = llm_result.get("missing_fields", [])
            # De-duplicate: prefer structural analysis for required fields
            structural_fields = {g["field"] for g in blocking_gaps}
            extra_llm = [m for m in llm_missing if m["field"] not in structural_fields]
            all_missing = blocking_gaps + non_blocking_gaps + extra_llm
            recommendation = llm_result.get(
                "recommendation", "Проверить список недостающих полей"
            )
        except Exception as exc:
            logger.warning("LLM enrichment failed for intake validator: %s", exc)
            all_missing = blocking_gaps + non_blocking_gaps
            recommendation = (
                "Предоставить недостающие обязательные поля для подачи заявки"
                if blocking_gaps
                else "Заявка заполнена. Рекомендуется проверить необязательные поля."
            )

        findings = {
            "is_complete": is_complete,
            "missing_fields": all_missing,
            "completeness_score": round(completeness_score, 2),
            "blocking_gaps": len(blocking_gaps),
            "non_blocking_gaps": len(non_blocking_gaps),
            "recommendation": recommendation,
        }

        summary = (
            f"Проверка полноты: {'✔ полна' if is_complete else '✗ неполна'}. "
            f"Критических пропусков: {len(blocking_gaps)}. "
            f"Некритических: {len(non_blocking_gaps)}. "
            f"Заполненность: {completeness_score:.0%}."
        )

        return StructuredAgentOutput(
            summary=summary,
            findings=findings,
            confidence=0.95 if not blocking_gaps else 0.90,
            human_review_required=len(blocking_gaps) > 3,
            next_actions=(
                ["request_missing_data_from_client"]
                if blocking_gaps
                else ["proceed_to_normalization"]
            ),
        )
