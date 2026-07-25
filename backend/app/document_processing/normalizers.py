"""Нормализаторы извлечённых значений.

Правило: нормализация никогда не выполняется молча. Каждый нормализатор
возвращает и исходное, и приведённое значение, чтобы специалист видел,
что именно система изменила, а преобразование попадало в audit log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Normalized:
    """Результат нормализации."""

    original: str
    value: str

    @property
    def changed(self) -> bool:
        return self.original != self.value


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_whitespace(value: str) -> Normalized:
    """Схлопнуть переносы строк и повторяющиеся пробелы.

    Нужно почти всегда: pdfplumber переносит длинные значения таблицы
    на несколько строк.
    """
    return Normalized(value, _collapse_spaces(value))


def normalize_digits(value: str) -> Normalized:
    """Оставить только цифры.

    ОГРН на титульном листе выписки печатается вразрядку —
    «1 1 8 4 2 0 5 0 1 9 1 2 9».
    """
    return Normalized(value, re.sub(r"\D", "", value or ""))


def normalize_legal_entity_name(value: str) -> Normalized:
    """Привести наименование юрлица к единому виду.

    Схлопывает пробелы и унифицирует кавычки до «ёлочек», как принято
    в реестровых документах. Регистр НЕ меняется: в ЕГРЮЛ наименование
    хранится прописными, и это юридически значимое написание.
    """
    text = _collapse_spaces(value)
    # Разные виды кавычек → «ёлочки».
    text = re.sub(r'["“”„″]', '"', text)
    text = re.sub(r'"([^"]*)"', r"«\1»", text)
    return Normalized(value, text)


def normalize_person_name(value: str) -> Normalized:
    """ФИО: схлопнуть пробелы, привести к виду «Иванов Иван Иванович».

    В ЕГРЮЛ ФИО хранится прописными (АЛЕКСЕЕНКО АНДРЕЙ СЕРГЕЕВИЧ),
    а в заявлении принято обычное написание.
    """
    text = _collapse_spaces(value)
    if text and text == text.upper():
        parts = [p.capitalize() for p in text.split(" ") if p]
        text = " ".join(parts)
    return Normalized(value, text)


def normalize_date(value: str) -> Normalized:
    """Оставить дату в формате ДД.ММ.ГГГГ."""
    match = re.search(r"\d{2}\.\d{2}\.\d{4}", value or "")
    return Normalized(value, match.group(0) if match else _collapse_spaces(value))


def normalize_inn(value: str) -> Normalized:
    return normalize_digits(value)


def normalize_ogrn(value: str) -> Normalized:
    return normalize_digits(value)


def normalize_kpp(value: str) -> Normalized:
    return normalize_digits(value)


def normalize_upper(value: str) -> Normalized:
    return Normalized(value, _collapse_spaces(value).upper())


def normalize_no_whitespace(value: str) -> Normalized:
    """Убрать все пробелы.

    Номер выписки переносится на следующую строку («ЮЭ9965-20-\n67739937»),
    из-за чего внутри значения появляется пробел.
    """
    return Normalized(value, re.sub(r"\s+", "", value or ""))


NORMALIZERS = {
    "whitespace": normalize_whitespace,
    "no_whitespace": normalize_no_whitespace,
    "digits": normalize_digits,
    "legal_entity_name": normalize_legal_entity_name,
    "person_name": normalize_person_name,
    "date": normalize_date,
    "inn": normalize_inn,
    "ogrn": normalize_ogrn,
    "kpp": normalize_kpp,
    "upper": normalize_upper,
}


def get_normalizer(name: str | None):
    """Вернуть нормализатор по имени из YAML.

    По умолчанию — схлопывание пробелов: безопасно для любого значения.
    """
    if not name:
        return normalize_whitespace
    if name not in NORMALIZERS:
        raise KeyError(
            f"Неизвестный нормализатор '{name}'. Доступны: {sorted(NORMALIZERS)}"
        )
    return NORMALIZERS[name]


# ---------------------------------------------------------------------------
# Сборка адреса
# ---------------------------------------------------------------------------

# В выписке ЕГРЮЛ адрес разложен по строкам таблицы: индекс, субъект,
# город, улица, дом, офис. В заявлении он нужен одной строкой.
ADDRESS_PART_ORDER = (
    "postal_code",
    "region",
    "district",
    "city",
    "settlement",
    "street",
    "house",
    "building",
    "office",
)


def compose_address(parts: dict[str, str]) -> Normalized:
    """Собрать адрес одной строкой из компонентов выписки.

    Порядок — от индекса к помещению, как принято в почтовом адресе РФ.
    Отсутствующие компоненты пропускаются, ничего не домысливается.
    """
    ordered = [
        _collapse_spaces(parts[key])
        for key in ADDRESS_PART_ORDER
        if parts.get(key) and _collapse_spaces(parts[key])
    ]
    composed = ", ".join(ordered)
    return Normalized(original=" | ".join(ordered), value=composed)
