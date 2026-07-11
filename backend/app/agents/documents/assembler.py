"""
DocumentAssemblyAgent — maps application fields to document template fields
and blocks generation on incompleteness.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

# Standard Роспатент application form fields
_ROSPATENT_FORM_FIELDS = [
    {"field_name": "заявитель_наименование", "field_label": "Полное наименование заявителя", "required": True, "format": "string"},
    {"field_name": "заявитель_инн", "field_label": "ИНН", "required": True, "format": "inn"},
    {"field_name": "заявитель_огрн", "field_label": "ОГРН / ОГРНИП", "required": True, "format": "ogrn"},
    {"field_name": "заявитель_адрес", "field_label": "Адрес для переписки", "required": True, "format": "address"},
    {"field_name": "заявитель_телефон", "field_label": "Телефон", "required": False, "format": "phone_ru"},
    {"field_name": "заявитель_email", "field_label": "Email", "required": True, "format": "email"},
    {"field_name": "обозначение_текст", "field_label": "Заявляемое обозначение (текст)", "required": True, "format": "string"},
    {"field_name": "обозначение_вид", "field_label": "Вид обозначения", "required": True, "format": "string"},
    {"field_name": "мкту_классы", "field_label": "Классы МКТУ", "required": True, "format": "classes_list"},
    {"field_name": "описание_товаров_услуг", "field_label": "Описание товаров и услуг", "required": True, "format": "string"},
    {"field_name": "заявитель_представитель", "field_label": "Имя представителя (пат. поверенного)", "required": False, "format": "string"},
    {"field_name": "дата_подачи", "field_label": "Дата подачи", "required": False, "format": "date"},
]


class DocumentAssemblyAgent(BaseAgent):
    """
    Maps application data to document template fields.
    Blocks document generation if required fields are missing.

    Input dict keys:
        application_data (dict): Full application data
        template_id (str, optional): defaults to 'form_заявка_роспатент_2023'
        strict_mode (bool, optional): strict format validation

    Output findings:
        mapped_fields, unmapped_fields, document_ready,
        missing_required_fields, warnings
    """

    agent_type = "documents.assembler"

    input_schema = {
        "type": "object",
        "required": ["application_data"],
        "properties": {
            "application_data": {"type": "object"},
            "template_id": {"type": "string"},
            "strict_mode": {"type": "boolean", "default": False},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        application_data = input_data.get("application_data", {})
        template_id = input_data.get("template_id", "form_заявка_роспатент_2023")
        strict_mode = input_data.get("strict_mode", False)

        variables = {
            "template_id": template_id,
            "application_data": application_data,
            "template_fields": _ROSPATENT_FORM_FIELDS,
            "strict_mode": strict_mode,
        }

        try:
            llm_result = await self._call_llm_structured(
                "docs.document_field_mapping", variables
            )
        except Exception as exc:
            logger.error("DocumentAssemblyAgent LLM call failed: %s", exc)
            llm_result = {
                "mapped_fields": {},
                "unmapped_fields": [f["field_name"] for f in _ROSPATENT_FORM_FIELDS],
                "template_id": template_id,
                "confidence": 0.0,
                "warnings": [],
                "format_corrections": {},
                "missing_required_fields": [
                    f["field_name"] for f in _ROSPATENT_FORM_FIELDS if f["required"]
                ],
                "document_ready": False,
            }

        document_ready = llm_result.get("document_ready", False)
        missing_required = llm_result.get("missing_required_fields", [])
        warnings = llm_result.get("warnings", [])
        confidence = llm_result.get("confidence", 0.9)

        # Enforce blocking rule: if required fields are missing, document is NOT ready
        if missing_required:
            document_ready = False
            llm_result["document_ready"] = False

        summary = (
            f"Сборка документа «{template_id}»: "
            f"{'готов к генерации' if document_ready else 'блокирован — отсутствуют обязательные поля'}. "
            f"Сопоставлено полей: {len(llm_result.get('mapped_fields', {}))}. "
            f"Предупреждений: {len(warnings)}."
        )

        missing_info = [
            {
                "field": f,
                "reason": "Обязательное поле для документа не заполнено",
                "who_provides": "client",
                "criticality": "blocking",
            }
            for f in missing_required
        ]

        next_actions: list[str] = []
        if document_ready:
            next_actions.append("generate_document")
            next_actions.append("proceed_to_submission")
        else:
            next_actions.append("request_missing_fields_for_document")
            next_actions.append("human_review_required")

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            missing_info=missing_info,
            confidence=confidence,
            human_review_required=not document_ready,
            next_actions=next_actions,
            raw_llm_output=str(llm_result),
        )
