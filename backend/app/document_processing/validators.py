"""Валидаторы российских реквизитов с проверкой контрольных сумм.

Проверка длины недостаточна: 13 цифр подряд встречаются в выписке ЕГРЮЛ
десятками (номера ГРН записей), и без контрольной суммы любой из них
сойдёт за ОГРН. Контрольная сумма отсеивает большинство ложных срабатываний.

Все функции чистые и не логируют значения — это персональные данные.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: str | None = None

    def __bool__(self) -> bool:
        return self.ok


_OK = ValidationResult(True)


def _digits_only(value: str) -> str:
    """Убрать пробелы и неразрывные пробелы.

    В выписке ЕГРЮЛ ОГРН на титульном листе печатается вразрядку:
    «1 1 8 4 2 0 5 0 1 9 1 2 9».
    """
    return re.sub(r"[\s   ]", "", value or "")


# ---------------------------------------------------------------------------
# ИНН
# ---------------------------------------------------------------------------

_INN_WEIGHTS_10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN_WEIGHTS_12_1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN_WEIGHTS_12_2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _checksum(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(w * d for w, d in zip(weights, digits)) % 11 % 10


def validate_inn(value: str, *, expect_length: int | None = None) -> ValidationResult:
    """Проверить ИНН (10 цифр — юрлицо, 12 — физлицо или ИП)."""
    raw = _digits_only(value)
    if not raw.isdigit():
        return ValidationResult(False, "ИНН должен состоять только из цифр")
    if len(raw) not in (10, 12):
        return ValidationResult(False, f"ИНН должен содержать 10 или 12 цифр, получено {len(raw)}")
    if expect_length is not None and len(raw) != expect_length:
        return ValidationResult(
            False,
            f"Ожидался ИНН длиной {expect_length} цифр, получено {len(raw)}",
        )

    digits = [int(c) for c in raw]
    if len(raw) == 10:
        if _checksum(digits[:9], _INN_WEIGHTS_10) != digits[9]:
            return ValidationResult(False, "Неверная контрольная сумма ИНН")
        return _OK

    if _checksum(digits[:10], _INN_WEIGHTS_12_1) != digits[10]:
        return ValidationResult(False, "Неверная контрольная сумма ИНН (11-й разряд)")
    if _checksum(digits[:11], _INN_WEIGHTS_12_2) != digits[11]:
        return ValidationResult(False, "Неверная контрольная сумма ИНН (12-й разряд)")
    return _OK


def validate_inn_legal_entity(value: str) -> ValidationResult:
    """ИНН юридического лица — строго 10 цифр."""
    return validate_inn(value, expect_length=10)


def validate_inn_individual(value: str) -> ValidationResult:
    """ИНН физлица или ИП — строго 12 цифр."""
    return validate_inn(value, expect_length=12)


# ---------------------------------------------------------------------------
# ОГРН / ОГРНИП
# ---------------------------------------------------------------------------

def _validate_ogrn_generic(value: str, length: int, name: str) -> ValidationResult:
    raw = _digits_only(value)
    if not raw.isdigit():
        return ValidationResult(False, f"{name} должен состоять только из цифр")
    if len(raw) != length:
        return ValidationResult(
            False, f"{name} должен содержать {length} цифр, получено {len(raw)}"
        )

    # Контрольный разряд: остаток от деления числа без последней цифры
    # на (длина - 2), взятый по модулю 10.
    divisor = length - 2
    control = int(raw[:-1]) % divisor % 10
    if control != int(raw[-1]):
        return ValidationResult(False, f"Неверная контрольная сумма {name}")

    # Первая цифра — признак записи; 0 не используется.
    if raw[0] == "0":
        return ValidationResult(False, f"{name} не может начинаться с нуля")
    return _OK


def validate_ogrn(value: str) -> ValidationResult:
    """ОГРН юридического лица — 13 цифр."""
    return _validate_ogrn_generic(value, 13, "ОГРН")


def validate_ogrnip(value: str) -> ValidationResult:
    """ОГРНИП индивидуального предпринимателя — 15 цифр."""
    return _validate_ogrn_generic(value, 15, "ОГРНИП")


# ---------------------------------------------------------------------------
# КПП
# ---------------------------------------------------------------------------

_KPP_RE = re.compile(r"^\d{4}[\dA-Z]{2}\d{3}$")


def validate_kpp(value: str) -> ValidationResult:
    """КПП — 9 знаков; 5-6 позиции могут быть буквами A-Z.

    Контрольной суммы у КПП нет — проверяется только структура.
    """
    raw = _digits_only(value).upper()
    if len(raw) != 9:
        return ValidationResult(False, f"КПП должен содержать 9 знаков, получено {len(raw)}")
    if not _KPP_RE.match(raw):
        return ValidationResult(False, "КПП не соответствует формату")
    return _OK


# ---------------------------------------------------------------------------
# Даты
# ---------------------------------------------------------------------------

def parse_ru_date(value: str) -> date | None:
    """Разобрать дату в формате ДД.ММ.ГГГГ."""
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", value or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%d.%m.%Y").date()
    except ValueError:
        return None


def validate_date(value: str) -> ValidationResult:
    """Проверить, что дата корректна и не находится в будущем."""
    parsed = parse_ru_date(value)
    if parsed is None:
        return ValidationResult(False, "Дата не распознана (ожидается ДД.ММ.ГГГГ)")
    if parsed > date.today():
        return ValidationResult(False, "Дата находится в будущем")
    if parsed.year < 1991:
        return ValidationResult(
            False, "Дата раньше 1991 года — вероятно, ошибка распознавания"
        )
    return _OK


# ---------------------------------------------------------------------------
# Реестр валидаторов (используется из YAML-конфигурации паттернов)
# ---------------------------------------------------------------------------

VALIDATORS = {
    "inn": validate_inn,
    "inn_legal_entity": validate_inn_legal_entity,
    "inn_individual": validate_inn_individual,
    "ogrn": validate_ogrn,
    "ogrnip": validate_ogrnip,
    "kpp": validate_kpp,
    "date": validate_date,
}


def get_validator(name: str | None):
    """Вернуть валидатор по имени из YAML или None."""
    if not name:
        return None
    if name not in VALIDATORS:
        raise KeyError(
            f"Неизвестный валидатор '{name}'. Доступны: {sorted(VALIDATORS)}"
        )
    return VALIDATORS[name]
