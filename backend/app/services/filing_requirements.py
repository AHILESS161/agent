"""Единый справочник применимости полей и приложений заявления.

Правила из этого модуля используются одновременно для публичного интерфейса,
проверки готовности ZIP и генерации идентификаторов в официальном DOCX. Здесь
нет проверки классов, анализа и пошлин: это отдельные процессные checkpoints,
а не поля заявления.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.infrastructure.database.models import TrademarkApplicationDraft


REQUIREMENTS_VERSION = "1.1.0"


@dataclass(frozen=True)
class RequirementSpec:
    code: str
    title: str
    action: str
    section: str = "data"
    kind: str = "field"
    applicable_to: tuple[str, ...] = ()
    required_for: tuple[str, ...] = ()
    mark_types: tuple[str, ...] = ()
    filing_methods: tuple[str, ...] = ()
    requires_representative: bool = False
    requires_power_of_attorney: bool = False
    requires_patent_attorney: bool = False
    requires_priority: bool = False
    value_path: str | None = None
    required: bool = False


FIELD_REQUIREMENTS = (
    RequirementSpec(
        "applicant_name", "Заявитель", "Укажите ФИО или наименование",
        value_path="client.full_name_or_company_name", required=True,
    ),
    RequirementSpec(
        "applicant_address", "Адрес заявителя", "Укажите полный адрес",
        value_path="client.address", required=True,
    ),
    RequirementSpec(
        "applicant_inn", "ИНН заявителя", "Укажите ИНН",
        applicable_to=("company", "sole_proprietor", "individual"),
        required_for=("company", "sole_proprietor"), value_path="client.inn",
    ),
    RequirementSpec(
        "applicant_registry_number", "ОГРН / ОГРНИП",
        "Укажите регистрационный номер",
        applicable_to=("company", "sole_proprietor"),
        required_for=("company", "sole_proprietor"),
        value_path="client.ogrn_or_ogrnip",
    ),
    RequirementSpec(
        "applicant_kpp", "КПП", "Укажите КПП, если он присвоен",
        applicable_to=("company",), value_path="client.kpp",
    ),
    RequirementSpec(
        "territory", "Страна заявителя", "Укажите Россию или другую страну",
        value_path="client.country_or_application.territory", required=True,
    ),
    RequirementSpec(
        "mark_name", "Обозначение", "Укажите заявляемое обозначение",
        value_path="application.mark_name", required=True,
    ),
    RequirementSpec(
        "mark_type", "Вид обозначения", "Выберите вид товарного знака",
        value_path="application.mark_type", required=True,
    ),
    RequirementSpec(
        "goods_services", "Товары и услуги",
        "Опишите товары или услуги, для которых регистрируется знак",
        value_path="application.goods_services_raw", required=True,
    ),
    RequirementSpec(
        "mark_description", "Описание обозначения",
        "Добавьте краткое описание знака",
        value_path="application.description_of_mark", required=True,
    ),
    RequirementSpec(
        "filing_method", "Способ подачи", "Выберите электронную или бумажную подачу",
        value_path="application.filing_method", required=True,
    ),
    RequirementSpec(
        "signatory_name", "Кто подпишет заявление", "Укажите ФИО подписанта",
        value_path="application.signatory_name", required=True,
    ),
    RequirementSpec(
        "representative_name", "Представитель", "Укажите ФИО представителя",
        value_path="representative.full_name", requires_representative=True, required=True,
    ),
    RequirementSpec(
        "representative_address", "Адрес представителя", "Укажите адрес представителя для переписки",
        value_path="representative.address", requires_representative=True, required=True,
    ),
    RequirementSpec(
        "representative_authority", "Основание полномочий", "Укажите, на каком основании действует представитель",
        value_path="representative.authority_type", requires_representative=True, required=True,
    ),
    RequirementSpec(
        "patent_attorney_number", "Номер патентного поверенного",
        "Укажите регистрационный номер патентного поверенного",
        value_path="representative.patent_attorney_registration_number",
        requires_patent_attorney=True, required=True,
    ),
    RequirementSpec(
        "poa_reference", "Реквизиты доверенности", "Укажите номер и дату доверенности",
        value_path="representative.poa_reference", requires_power_of_attorney=True, required=True,
    ),
    RequirementSpec(
        "signatory_position", "Должность подписанта",
        "Укажите должность руководителя или представителя",
        applicable_to=("company",), required_for=("company",),
        value_path="application.signatory_position",
    ),
    RequirementSpec(
        "signature_date", "Дата подписания",
        "Укажите дату подписания заявления",
        value_path="application.signature_date", required=True,
    ),
    RequirementSpec(
        "paper_certificate", "Бумажное свидетельство",
        "Выберите только при необходимости бумажного экземпляра",
        value_path="application.request_paper_certificate",
    ),
)


ATTACHMENT_REQUIREMENTS = (
    RequirementSpec(
        "mark_image", "Изображение обозначения", "Загрузите изображение знака",
        kind="attachment", mark_types=("figurative", "combined"), required=True,
    ),
    RequirementSpec(
        "mark_audio", "Аудиозапись звукового обозначения",
        "Загрузите аудиозапись звукового знака",
        kind="attachment", mark_types=("sound",), required=True,
    ),
    RequirementSpec(
        "power_of_attorney", "Доверенность представителя",
        "Загрузите доверенность", kind="attachment",
        requires_power_of_attorney=True, required=True,
    ),
    RequirementSpec(
        "priority_proof", "Документ о заявленном приоритете",
        "Загрузите подтверждение приоритета отдельным файлом",
        kind="attachment", requires_priority=True, required=True,
    ),
)


PROCEDURAL_REQUIREMENTS = (
    RequirementSpec(
        "electronic_signature_notice", "Подписание электронной заявки",
        "Подпишите заявление электронной подписью в официальном сервисе",
        kind="instruction", filing_methods=("electronic",),
    ),
    RequirementSpec(
        "paper_signature_notice", "Подписание бумажной заявки",
        "После печати поставьте собственноручную подпись в оставленном поле",
        kind="instruction", filing_methods=("paper",),
    ),
)


def _enum_value(value: Any) -> str | None:
    return getattr(value, "value", value) if value is not None else None


def _client_type(application: TrademarkApplicationDraft) -> str | None:
    client = getattr(application, "client", None)
    return _enum_value(getattr(client, "type", None))


def _value(application: TrademarkApplicationDraft, path: str | None) -> Any:
    if not path:
        return None
    client = getattr(application, "client", None)
    if path == "client.country_or_application.territory":
        return getattr(client, "country", None) or getattr(application, "territory", None)
    root: Any = client if path.startswith("client.") else application
    attribute = path.split(".", 1)[1]
    return getattr(root, attribute, None) if root is not None else None


def applicant_identifier_fields(applicant_type: str | None) -> tuple[tuple[str, str], ...]:
    """Подписи и поля идентификаторов для официального DOCX."""
    return {
        "company": (
            ("ОГРН", "application.applicant.ogrn"),
            ("ИНН", "application.applicant.inn"),
            ("КПП", "application.applicant.kpp"),
        ),
        "sole_proprietor": (
            ("ОГРНИП", "application.applicant.ogrn"),
            ("ИНН", "application.applicant.inn"),
        ),
        "individual": (("ИНН", "application.applicant.inn"),),
    }.get(
        applicant_type,
        (
            ("ОГРН", "application.applicant.ogrn"),
            ("ИНН", "application.applicant.inn"),
            ("КПП", "application.applicant.kpp"),
        ),
    )


def filing_requirements_manifest(
    application: TrademarkApplicationDraft,
    *,
    has_representative: bool = False,
    representative: Any | None = None,
    available_attachments: set[str] | None = None,
) -> dict[str, Any]:
    """Вернуть применимость, обязательность и готовность каждого правила."""
    attachments = available_attachments or set()
    applicant_type = _client_type(application)
    mark_type = _enum_value(getattr(application, "mark_type", None))
    filing_method = getattr(application, "filing_method", None) or "electronic"
    representative = representative or getattr(application, "representative", None)
    has_representative = has_representative or representative is not None
    authority_type = getattr(representative, "authority_type", None) or (
        "power_of_attorney" if has_representative else None
    )
    is_patent_attorney = bool(getattr(representative, "is_patent_attorney", False))
    result: list[dict[str, Any]] = []

    for spec in (*FIELD_REQUIREMENTS, *ATTACHMENT_REQUIREMENTS, *PROCEDURAL_REQUIREMENTS):
        applicable = True
        if spec.applicable_to and applicant_type not in spec.applicable_to:
            applicable = False
        if spec.mark_types and mark_type not in spec.mark_types:
            applicable = False
        if spec.filing_methods and filing_method not in spec.filing_methods:
            applicable = False
        if spec.requires_representative and not has_representative:
            applicable = False
        if spec.requires_power_of_attorney and (
            not has_representative or authority_type != "power_of_attorney"
        ):
            applicable = False
        if spec.requires_patent_attorney and not is_patent_attorney:
            applicable = False
        if spec.requires_priority and not bool(getattr(application, "priority_claim", None)):
            applicable = False

        required = applicable and (spec.required or applicant_type in spec.required_for)
        if spec.kind == "attachment":
            satisfied = spec.code in attachments
        elif spec.kind == "instruction":
            satisfied = True
        else:
            if spec.value_path and spec.value_path.startswith("representative."):
                value = getattr(representative, spec.value_path.split(".", 1)[1], None)
            else:
                value = _value(application, spec.value_path)
            # Ложное значение допустимо для осознанного необязательного checkbox.
            satisfied = value is not None and (not isinstance(value, str) or bool(value.strip()))

        result.append(
            {
                "code": spec.code,
                "title": spec.title,
                "action": spec.action,
                "section": spec.section,
                "kind": spec.kind,
                "applicable": applicable,
                "required": required,
                "satisfied": satisfied if applicable else True,
            }
        )

    return {
        "version": REQUIREMENTS_VERSION,
        "applicant_type": applicant_type,
        "mark_type": mark_type,
        "filing_method": filing_method,
        "requirements": result,
    }


def missing_required_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in manifest["requirements"]
        if item["applicable"] and item["required"] and not item["satisfied"]
    ]
