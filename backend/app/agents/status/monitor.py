"""
StatusMonitoringAgent — polls external registry for status updates
and generates change notifications when status changes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.agents.base import BaseAgent, StructuredAgentOutput
from app.infrastructure.providers.base import TrademarkRegistryProvider

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"registered", "refused", "withdrawn", "cancelled"})


class StatusMonitoringAgent(BaseAgent):
    """
    Polls the external registry for application status updates.

    Input dict keys:
        external_id (str): ID from SubmissionAgent output
        current_status (str): Last known internal status
        application_id (str, optional): Internal application reference

    Output findings:
        external_status, status_changed, new_status, previous_status,
        is_terminal, details, notification_required
    """

    agent_type = "status.monitor"

    input_schema = {
        "type": "object",
        "required": ["external_id", "current_status"],
        "properties": {
            "external_id": {"type": "string"},
            "current_status": {"type": "string"},
            "application_id": {"type": "string"},
        },
    }

    def __init__(self, prompt_registry, llm_provider, registry_provider: TrademarkRegistryProvider):
        super().__init__(prompt_registry, llm_provider)
        self.registry_provider = registry_provider

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        external_id = input_data.get("external_id", "")
        current_status = input_data.get("current_status", "filed")

        if not external_id:
            return StructuredAgentOutput(
                summary="Ошибка: не указан external_id для проверки статуса.",
                findings={"error": "missing external_id"},
                error="missing external_id",
                human_review_required=True,
            )

        try:
            ext_result = await self.registry_provider.get_status(external_id)
        except Exception as exc:
            logger.error("StatusMonitoringAgent: registry call failed: %s", exc)
            return StructuredAgentOutput(
                summary=f"Ошибка при запросе статуса: {exc}",
                findings={"error": str(exc)},
                confidence=0.0,
                human_review_required=True,
                error=str(exc),
                next_actions=["retry_status_check"],
            )

        new_status = ext_result.status
        status_changed = new_status != current_status
        is_terminal = new_status in _TERMINAL_STATUSES

        findings = {
            "external_status": new_status,
            "status_changed": status_changed,
            "new_status": new_status,
            "previous_status": current_status,
            "is_terminal": is_terminal,
            "details": ext_result.details,
            "updated_at": ext_result.updated_at,
            "notification_required": status_changed,
        }

        if status_changed:
            summary = (
                f"Статус изменился: {current_status} → {new_status} "
                f"({'терминальный' if is_terminal else 'промежуточный'})."
            )
        else:
            summary = f"Статус без изменений: {current_status}. Последнее обновление: {ext_result.updated_at}."

        next_actions: list[str] = []
        if status_changed:
            next_actions.append("send_status_change_notification_to_client")
            next_actions.append("update_internal_status")
        if is_terminal:
            next_actions.append("close_monitoring_task")
        else:
            next_actions.append("schedule_next_status_poll")

        return StructuredAgentOutput(
            summary=summary,
            findings=findings,
            confidence=0.99,
            next_actions=next_actions,
            human_review_required=new_status in ("refused", "office_action"),
        )
