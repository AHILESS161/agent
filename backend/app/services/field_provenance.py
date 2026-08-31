"""Понятное происхождение значений, показанных пользователю.

Интерфейс не должен угадывать источник по принципу «поле непустое — значит
оно из документа». Значение считается извлечённым из документа только когда
оно совпадает с сохранённым :class:`ExtractedField`; предложенным системой —
когда оно совпадает с зафиксированным результатом автоматической подготовки.
Любое изменённое человеком значение автоматически становится пользовательским.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    AuditLog,
    DocumentKind,
    DocumentPage,
    ExtractedField,
    SourceDocument,
    TrademarkApplicationDraft,
)


FIELD_SOURCES_VERSION = "1.0.0"


@dataclass(frozen=True)
class FieldSpec:
    code: str
    value: Callable[[TrademarkApplicationDraft], Any]
    document_paths: tuple[str, ...] = ()
    default_system_value: Any = None


def _client_value(attribute: str) -> Callable[[TrademarkApplicationDraft], Any]:
    return lambda application: (
        getattr(application.client, attribute, None) if application.client else None
    )


FIELD_SPECS = (
    FieldSpec(
        "applicant_name",
        _client_value("full_name_or_company_name"),
        (
            "registry.legal_entity.full_name",
            "registry.sole_proprietor.full_name",
        ),
    ),
    FieldSpec(
        "applicant_inn",
        _client_value("inn"),
        ("registry.legal_entity.inn", "registry.sole_proprietor.inn"),
    ),
    FieldSpec(
        "applicant_registry_number",
        _client_value("ogrn_or_ogrnip"),
        ("registry.legal_entity.ogrn", "registry.sole_proprietor.ogrnip"),
    ),
    FieldSpec("applicant_kpp", _client_value("kpp"), ("registry.legal_entity.kpp",)),
    FieldSpec(
        "applicant_address",
        _client_value("address"),
        ("registry.legal_entity.address.full",),
    ),
    FieldSpec("territory", _client_value("country"), default_system_value="RU"),
    FieldSpec("applicant_email", _client_value("email")),
    FieldSpec("applicant_phone", _client_value("phone")),
    FieldSpec("mark_type", lambda application: application.mark_type),
    FieldSpec("mark_name", lambda application: application.mark_name),
    FieldSpec("mark_text", lambda application: application.mark_text),
    FieldSpec("mark_image", lambda application: application.mark_image_file_id),
    FieldSpec("mark_audio", lambda _application: None),
    FieldSpec(
        "goods_services",
        lambda application: application.goods_services_raw
        or application.business_description,
        ("registry.sole_proprietor.main_activity",),
    ),
    FieldSpec("mark_description", lambda application: application.description_of_mark),
    FieldSpec("colors_claimed", lambda application: application.colors_claimed),
    FieldSpec("transliteration", lambda application: application.transliteration),
    FieldSpec("translation", lambda application: application.translation),
    FieldSpec(
        "filing_method",
        lambda application: application.filing_method,
        default_system_value="electronic",
    ),
    FieldSpec(
        "paper_certificate",
        lambda application: application.request_paper_certificate,
    ),
    FieldSpec(
        "signatory_name",
        lambda application: application.signatory_name,
        (
            "registry.sole_proprietor.full_name",
            "registry.legal_entity.director.full_name",
        ),
    ),
    FieldSpec(
        "signatory_position",
        lambda application: application.signatory_position,
        ("registry.legal_entity.director.position",),
    ),
    FieldSpec("signature_date", lambda application: application.signature_date),
)


SYSTEM_AUDIT_ACTIONS = {
    "application.mark_language.suggested",
    "application.mark_description.suggested",
    "application.mark_details.suggested",
}
PROFILE_AUDIT_ACTION = "application.prefilled_from_profile"

SYSTEM_KEY_TO_CODE = {
    "description": "mark_description",
    "description_of_mark": "mark_description",
    "colors": "colors_claimed",
    "colors_claimed": "colors_claimed",
    "transliteration": "transliteration",
    "translation": "translation",
}
PROFILE_KEY_TO_CODE = {
    "full_name_or_company_name": "applicant_name",
    "inn": "applicant_inn",
    "ogrn_or_ogrnip": "applicant_registry_number",
    "kpp": "applicant_kpp",
    "address": "applicant_address",
    "country": "territory",
    "email": "applicant_email",
    "phone": "applicant_phone",
}


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _normalized(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    text = unicodedata.normalize("NFKC", str(_plain(value))).casefold()
    return "".join(character for character in text if character.isalnum())


def _is_filled(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    return value is not None and bool(str(_plain(value)).strip())


def _document_detail(filename: str | None, page: int | None) -> str:
    if filename and page:
        return f"Значение найдено в файле «{filename}», страница {page}. Сверьте его с оригиналом."
    if filename:
        return f"Значение найдено в файле «{filename}». Сверьте его с оригиналом."
    return "Значение извлечено из загруженного документа. Сверьте его с оригиналом."


def _source_item(
    code: str,
    *,
    source: str,
    filled: bool,
    detail: str | None = None,
) -> dict[str, Any]:
    labels = {
        "document": "Из документа — проверьте",
        "system": "Предложено системой — проверьте",
        "user": "Введено вами" if filled else "Заполнить вручную",
        "rospatent": "Заполнит Роспатент",
        "profile": "Из вашего профиля — проверьте",
    }
    details = {
        "system": "Система предложила это значение автоматически. Проверьте его перед подачей.",
        "user": (
            "Значение сохранено после ввода или изменения пользователем."
            if filled
            else "Этого значения нет в документах — укажите его самостоятельно."
        ),
        "rospatent": "Это служебное поле появится после приёма или регистрации заявки.",
        "profile": "Значение подставлено из сохранённых данных заявителя. Проверьте его перед подачей.",
    }
    return {
        "code": code,
        "source": source,
        "label": labels[source],
        "detail": detail or details.get(source) or "",
        "filled": filled,
        "verification_required": source in {"document", "system", "profile"},
    }


def _director_candidates(
    extracted: list[tuple[ExtractedField, str | None]],
) -> list[tuple[str, str | None, int | None]]:
    """Собрать ФИО руководителя из трёх строк одной выписки."""
    grouped: dict[int | None, dict[str, tuple[str, str | None, int | None]]] = defaultdict(dict)
    prefixes = {
        "registry.legal_entity.director.last_name": "last",
        "registry.legal_entity.director.first_name": "first",
        "registry.legal_entity.director.middle_name": "middle",
    }
    for field, filename in extracted:
        part = prefixes.get(field.field_path)
        value = field.normalized_value or field.raw_value
        if part and value:
            grouped[field.document_id][part] = (value, filename, field.page_number)

    result: list[tuple[str, str | None, int | None]] = []
    for parts in grouped.values():
        value = " ".join(
            parts[key][0] for key in ("last", "first", "middle") if key in parts
        )
        if value:
            first = next(iter(parts.values()))
            result.append((value, first[1], first[2]))
    return result


async def field_sources_manifest(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
) -> dict[str, Any]:
    """Вернуть единый серверный контракт источников полей клиентской формы."""
    extracted = list(
        (
            await session.execute(
                select(ExtractedField, SourceDocument.original_filename)
                .outerjoin(SourceDocument, SourceDocument.id == ExtractedField.document_id)
                .where(ExtractedField.application_id == application.id)
                .order_by(ExtractedField.created_at.desc())
            )
        ).all()
    )
    by_path: dict[str, list[tuple[str, str | None, int | None]]] = defaultdict(list)
    for field, filename in extracted:
        value = field.normalized_value or field.raw_value
        if value:
            by_path[field.field_path].append((value, filename, field.page_number))
    by_path["registry.legal_entity.director.full_name"].extend(
        _director_candidates(extracted)
    )

    audits = list(
        (
            await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.application_id == application.id,
                    AuditLog.action.in_((*SYSTEM_AUDIT_ACTIONS, PROFILE_AUDIT_ACTION)),
                )
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            )
        )
        .scalars()
        .all()
    )
    system_values: dict[str, list[Any]] = defaultdict(list)
    profile_values: dict[str, list[Any]] = defaultdict(list)
    for audit in audits:
        for key, value in (audit.new_value_json or {}).items():
            code = (PROFILE_KEY_TO_CODE if audit.action == PROFILE_AUDIT_ACTION else SYSTEM_KEY_TO_CODE).get(key)
            if code and _is_filled(value):
                (profile_values if audit.action == PROFILE_AUDIT_ACTION else system_values)[code].append(value)

    documents = list(
        (
            await session.execute(
                select(SourceDocument).where(SourceDocument.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    active_image = next(
        (
            item
            for item in documents
            if str(item.id) == str(application.mark_image_file_id)
            and item.document_kind is DocumentKind.mark_image
        ),
        None,
    )
    active_audio = next(
        (item for item in reversed(documents) if item.document_kind is DocumentKind.mark_audio),
        None,
    )
    image_text = ""
    if active_image:
        image_text = "\n".join(
            value.strip()
            for value in (
                await session.execute(
                    select(DocumentPage.text_content)
                    .where(DocumentPage.document_id == active_image.id)
                    .order_by(DocumentPage.page_number)
                )
            ).scalars()
            if value and value.strip()
        )

    items: list[dict[str, Any]] = []
    for spec in FIELD_SPECS:
        value = active_audio.id if spec.code == "mark_audio" and active_audio else spec.value(application)
        filled = _is_filled(value)
        matched_document: tuple[str, str | None, int | None] | None = None
        for path in spec.document_paths:
            matched_document = next(
                (
                    candidate
                    for candidate in by_path.get(path, [])
                    if filled and _normalized(candidate[0]) == _normalized(value)
                ),
                None,
            )
            if matched_document:
                break

        if matched_document:
            items.append(
                _source_item(
                    spec.code,
                    source="document",
                    filled=True,
                    detail=_document_detail(matched_document[1], matched_document[2]),
                )
            )
            continue
        if spec.code == "mark_text" and image_text and _normalized(image_text) == _normalized(value):
            items.append(
                _source_item(
                    spec.code,
                    source="system",
                    filled=filled,
                    detail="Текст распознан на загруженном изображении. Обязательно сверьте его с логотипом.",
                )
            )
            continue
        if any(_normalized(candidate) == _normalized(value) for candidate in system_values[spec.code]):
            items.append(_source_item(spec.code, source="system", filled=filled))
            continue
        if any(_normalized(candidate) == _normalized(value) for candidate in profile_values[spec.code]):
            items.append(_source_item(spec.code, source="profile", filled=filled))
            continue
        if filled and spec.default_system_value is not None and _normalized(value) == _normalized(spec.default_system_value):
            items.append(
                _source_item(
                    spec.code,
                    source="system",
                    filled=True,
                    detail=(
                        "Россия выбрана по умолчанию. Измените страну, если заявитель иностранный."
                        if spec.code == "territory"
                        else "Это значение выбрано системой по умолчанию. Проверьте, что оно вам подходит."
                    ),
                )
            )
            continue
        if spec.code in {"mark_image", "mark_audio"} and filled:
            items.append(
                _source_item(
                    spec.code,
                    source="user",
                    filled=True,
                    detail="Файл загружен вами в эту заявку.",
                )
            )
            continue
        items.append(_source_item(spec.code, source="user", filled=filled))

    for code in (
        "rospatent_application_number",
        "rospatent_filing_date",
        "rospatent_registration_number",
        "rospatent_registration_date",
    ):
        items.append(_source_item(code, source="rospatent", filled=False))

    return {"version": FIELD_SOURCES_VERSION, "fields": items}
