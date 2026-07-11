"""
SubmissionAgent — submits the prepared application to the registry provider
(Роспатент via adapter) and records the external ID.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput
from app.infrastructure.providers.base import SubmissionPayload, TrademarkRegistryProvider

logger = logging.getLogger(__name__)


class SubmissionAgent(BaseAgent):
    """
    Submits an application through the provider adapter.

    Requires a registry provider to be injected.

    Input dict keys:
        applicant_data (dict)
        mark_data (dict)
        goods_services (list[dict])
        classes (list[int])
        description (str)
        documents (list[str])

    Output findings:
        success, external_id, submission_timestamp
    """

    agent_type = "submission.submitter"

    input_schema = {
        "type": "object",
        "required": [
            "applicant_data",
            "mark_data",
            "goods_services",
            "classes",
            "description",
            "documents",
        ],
        "properties": {
            "applicant_data": {"type": "object"},
            "mark_data": {"type": "object"},
            "goods_services": {"type": "array"},
            "classes": {"type": "array", "items": {"type": "integer"}},
            "description": {"type": "string"},
            "documents": {"type": "array", "items": {"type": "string"}},
        },
    }

    def __init__(self, prompt_registry, llm_provider, registry_provider: TrademarkRegistryProvider):
        super().__init__(prompt_registry, llm_provider)
        self.registry_provider = registry_provider

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        payload = SubmissionPayload(
            applicant_data=input_data.get("applicant_data", {}),
            mark_data=input_data.get("mark_data", {}),
            goods_services=input_data.get("goods_services", []),
            classes=input_data.get("classes", []),
            description=input_data.get("description", ""),
            documents=input_data.get("documents", []),
        )

        try:
            result = await self.registry_provider.submit_application(payload)
        except Exception as exc:
            logger.error("SubmissionAgent: provider call failed: %s", exc)
            return StructuredAgentOutput(
                summary=f"Ошибка при подаче заявки: {exc}",
                findings={"success": False, "error": str(exc)},
                confidence=0.0,
                human_review_required=True,
                error=str(exc),
                next_actions=["retry_submission", "human_review_required"],
            )

        if result.success:
            summary = f"Заявка успешно подана. Внешний ID: {result.external_id}."
            next_actions = ["monitor_submission_status"]
        else:
            summary = f"Подача не удалась: {result.error_message}."
            next_actions = ["human_review_required", "retry_submission"]

        return StructuredAgentOutput(
            summary=summary,
            findings={
                "success": result.success,
                "external_id": result.external_id,
                "error_message": result.error_message,
            },
            confidence=0.99 if result.success else 0.0,
            human_review_required=not result.success,
            next_actions=next_actions,
        )
