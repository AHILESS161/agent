"""Измеримая оценка качества извлечения выписок ЕГРЮЛ и ЕГРИП.

Модуль не улучшает результат задним числом и не подменяет юридическую
проверку. Он сопоставляет извлечённые значения с заранее размеченным эталоном
и явно перечисляет поля, которые нельзя безопасно предзаполнить.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

from app.document_processing.extractors.registry import (
    ExtractedFieldResult,
    extract_registry_fields,
)
from app.infrastructure.database.models import FieldStatus


DEFAULT_MIN_CONFIDENCE = 0.75


def _canonical(value: str | None) -> str:
    """Сравнить содержание, не считая регистр и лишние пробелы ошибкой."""

    return re.sub(r"\s+", " ", value or "").strip().casefold()


@dataclass(frozen=True)
class FieldEvaluation:
    field_id: str
    expected: str
    actual: str | None
    status: str
    confidence: float | None
    exact: bool
    requires_manual_review: bool
    review_reason: str | None


@dataclass(frozen=True)
class RegistryEvaluationReport:
    document_kind: str
    total_expected: int
    exact_fields: int
    missing_fields: int
    wrong_fields: int
    exact_match_rate: float
    required_match_rate: float
    safe_to_prefill: bool
    manual_review_fields: tuple[str, ...]
    fields: tuple[FieldEvaluation, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _review_reason(
    result: ExtractedFieldResult | None,
    *,
    exact: bool,
    min_confidence: float,
) -> str | None:
    if result is None or result.status is FieldStatus.missing:
        return "Поле не найдено — заполните его вручную по документу"
    if result.status is FieldStatus.conflict:
        return "В документе найдено несколько значений — выберите верное"
    if result.status is FieldStatus.needs_review:
        return result.validation_error or "Значение не прошло автоматическую проверку"
    if not exact:
        return "Распознанное значение не совпало с эталоном"
    if result.confidence is None or result.confidence < min_confidence:
        return "Недостаточно надёжное распознавание — сверьте поле с документом"
    return None


def evaluate_registry_extraction(
    pages: Iterable[tuple[int, str]],
    document_kind: str,
    expected: Mapping[str, str],
    *,
    required_fields: Sequence[str] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> RegistryEvaluationReport:
    """Получить метрики для одного размеченного документа.

    ``expected`` использует полные идентификаторы полей извлекателя, например
    ``registry.legal_entity.inn``. ``required_fields`` определяет минимальный
    набор, без которого результат нельзя безопасно предложить пользователю.
    """

    results = {
        item.field_id: item
        for item in extract_registry_fields(pages, document_kind=document_kind)
    }
    required = set(required_fields or expected.keys())
    rows: list[FieldEvaluation] = []

    for field_id, expected_value in expected.items():
        result = results.get(field_id)
        actual = result.normalized_value if result else None
        exact = _canonical(actual) == _canonical(expected_value)
        reason = _review_reason(result, exact=exact, min_confidence=min_confidence)
        rows.append(
            FieldEvaluation(
                field_id=field_id,
                expected=expected_value,
                actual=actual,
                status=(result.status.value if result else FieldStatus.missing.value),
                confidence=result.confidence if result else None,
                exact=exact,
                requires_manual_review=reason is not None,
                review_reason=reason,
            )
        )

    exact_fields = sum(row.exact for row in rows)
    missing_fields = sum(row.actual is None for row in rows)
    wrong_fields = len(rows) - exact_fields - missing_fields
    required_rows = [row for row in rows if row.field_id in required]
    exact_required = sum(row.exact for row in required_rows)
    unsafe_required = [
        row.field_id for row in required_rows if row.requires_manual_review
    ]

    return RegistryEvaluationReport(
        document_kind=document_kind,
        total_expected=len(rows),
        exact_fields=exact_fields,
        missing_fields=missing_fields,
        wrong_fields=wrong_fields,
        exact_match_rate=round(exact_fields / len(rows), 4) if rows else 1.0,
        required_match_rate=(
            round(exact_required / len(required_rows), 4) if required_rows else 1.0
        ),
        safe_to_prefill=not unsafe_required,
        manual_review_fields=tuple(unsafe_required),
        fields=tuple(rows),
    )

