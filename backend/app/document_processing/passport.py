"""Минимальное извлечение данных заявителя из российского паспорта.

Паспорт содержит больше персональных данных, чем требуется для заявки на
товарный знак. Поэтому этот модуль намеренно возвращает только ФИО и адрес
регистрации. Серия, номер, дата рождения, сведения о выдаче и код
подразделения не извлекаются и не должны попадать в формируемый пакет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PassportPrefillField:
    field_id: str
    label: str
    value: str
    form_target: str


_NAME_LABELS = "фамилия|имя|отчество|surname|name|patronymic"
_ADDRESS_STOP = (
    r"(?:дата\s+рождения|место\s+рождения|паспорт\s+выдан|код\s+подразделения|"
    r"семейное\s+положение|воинская\s+обязанность|$)"
)


def _label_value(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?:^|\n)\s*(?:{label})\s*[:\-]?\s*"
        rf"([А-ЯЁ][А-ЯЁа-яё'\-]+)(?=\s*(?:\n|{_NAME_LABELS}\b))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).strip(" .,-")
    return value.title() if value else None


def _address(text: str) -> str | None:
    match = re.search(
        rf"(?:место\s+жительства|адрес\s+регистрации|"
        rf"зарегистрирован(?:а)?(?:\s+по\s+месту\s+жительства)?(?:\s+по\s+адресу)?)"
        rf"\s*[:\-]?\s*(.{{10,240}}?)(?=\s*{_ADDRESS_STOP})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .,-")
    # Короткие обрывки OCR и строки без цифр/слов не предлагаем пользователю.
    if len(value) < 10 or len(re.findall(r"[А-ЯЁа-яёA-Za-z0-9]+", value)) < 3:
        return None
    return value


def extract_passport_prefill(text: str) -> list[PassportPrefillField]:
    """Вернуть только необходимые для карточки заявителя поля паспорта."""
    normalized = text.replace("\r", "\n")
    last_name = _label_value(normalized, "фамилия|surname")
    first_name = _label_value(normalized, "имя|name")
    middle_name = _label_value(normalized, "отчество|patronymic")

    fields: list[PassportPrefillField] = []
    full_name = " ".join(part for part in (last_name, first_name, middle_name) if part)
    if last_name and first_name:
        fields.append(
            PassportPrefillField(
                field_id="passport.applicant.full_name",
                label="ФИО заявителя",
                value=full_name,
                form_target="name",
            )
        )

    registration_address = _address(normalized)
    if registration_address:
        fields.append(
            PassportPrefillField(
                field_id="passport.applicant.registration_address",
                label="Адрес регистрации",
                value=registration_address,
                form_target="address",
            )
        )
    return fields
