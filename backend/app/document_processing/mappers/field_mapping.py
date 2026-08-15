"""Сопоставление: реестровая выписка -> карточка дела -> заявление.

Модуль строит таблицу сверки для специалиста. Он НЕ переносит значения
в заявление: перенос возможен только после явного подтверждения человеком.

Для каждого поля показывается:
    - значение из реестровой справки (и его источник: страница, паттерн);
    - текущее значение в карточке дела;
    - поле заявления, куда значение попадёт;
    - статус: matched / missing / conflict / needs_review / confirmed;
    - какие действия доступны специалисту.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.document_processing.extractors.registry import ExtractedFieldResult
from app.infrastructure.database.models import FieldStatus

MAPPINGS_DIR = Path(__file__).resolve().parents[3] / "resources" / "field_mappings"

# Действия, доступные специалисту по каждому полю.
ACTION_ACCEPT = "accept"
ACTION_EDIT = "edit"
ACTION_REJECT = "reject"
ACTION_LEAVE_EMPTY = "leave_empty"

# Статусы, означающие, что специалист уже принял решение по полю.
# Автоматические правила такие поля не пересчитывают.
_DECIDED_BY_SPECIALIST = frozenset(
    {FieldStatus.confirmed, FieldStatus.rejected, FieldStatus.left_empty}
)


@dataclass
class MappingRow:
    """Одна строка таблицы сверки."""

    label: str
    registry_field: str | None
    case_field: str
    application_field: str | None
    status: FieldStatus

    # Человекочитаемое имя поля бланка: технический путь
    # специалисту ничего не говорит.
    application_field_label: str | None = None

    registry_value: str | None = None
    registry_raw_value: str | None = None
    case_value: str | None = None
    default_value: str | None = None

    confidence: float | None = None
    page_number: int | None = None
    pattern_id: str | None = None
    source_snippet: str = ""
    extraction_method: str | None = None

    required_for_application: bool = False
    critical: bool = False
    is_sensitive: bool = False
    normalization_changed: bool = False
    validation_error: str | None = None
    note: str | None = None

    candidates: list[dict[str, Any]] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)

    @property
    def blocks_document_generation(self) -> bool:
        """Мешает ли поле сформировать черновик заявления.

        Критичные обязательные поля не должны попадать в документ
        в статусе unconfirmed / conflict / needs_review.
        """
        if not self.required_for_application:
            return False
        return self.status in (
            FieldStatus.missing,
            FieldStatus.conflict,
            FieldStatus.needs_review,
        )


@lru_cache(maxsize=4)
def load_mapping_config(name: str = "registry_to_application") -> dict[str, Any]:
    """Загрузить версионируемую конфигурацию маппинга."""
    path = MAPPINGS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Файл маппинга не найден: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class FieldMappingEngine:
    """Строит таблицу сверки по конфигурации маппинга."""

    def __init__(self, mapping_name: str = "registry_to_application") -> None:
        self.config = load_mapping_config(mapping_name)
        self.mapping_name = mapping_name

    @property
    def version(self) -> int:
        return int(self.config.get("version", 0))

    def build(
        self,
        extracted: Iterable[ExtractedFieldResult],
        case_values: dict[str, str] | None = None,
        client_type: str | None = None,
    ) -> list[MappingRow]:
        """Сопоставить извлечённые поля с полями дела и заявления.

        ``client_type`` (company/sole_proprietor/individual) отбирает
        применимые строки: у юрлица и ИП разные реестровые поля, и
        показывать заявителю-ИП пустые строки ЕГРЮЛ (и наоборот) —
        значит выдавать неполноту за пропуск.
        """
        by_field_id = {result.field_id: result for result in extracted}
        case_values = case_values or {}
        rows: list[MappingRow] = []

        for spec in self.config.get("mappings", []):
            applies_to = spec.get("applies_to")
            if client_type and applies_to and client_type not in applies_to:
                continue
            rows.append(self._build_row(spec, by_field_id, case_values))
        return rows

    def _build_row(
        self,
        spec: dict[str, Any],
        by_field_id: dict[str, ExtractedFieldResult],
        case_values: dict[str, str],
    ) -> MappingRow:
        registry_field = spec.get("registry_field")
        case_field = spec["case_field"]
        extracted = by_field_id.get(registry_field) if registry_field else None
        case_value = case_values.get(case_field)

        row = MappingRow(
            label=spec.get("label", case_field),
            registry_field=registry_field,
            case_field=case_field,
            application_field=spec.get("application_field"),
            application_field_label=spec.get("application_field_label"),
            status=FieldStatus.missing,
            case_value=case_value,
            default_value=spec.get("default_value"),
            required_for_application=bool(spec.get("required_for_application", False)),
            critical=bool(spec.get("critical", False)),
            is_sensitive=bool(spec.get("sensitive", False)),
            note=spec.get("note"),
        )

        if extracted is not None:
            row.registry_value = extracted.normalized_value
            row.registry_raw_value = extracted.value
            row.confidence = extracted.confidence
            row.page_number = extracted.page_number
            row.pattern_id = extracted.pattern_id
            row.source_snippet = extracted.source_snippet
            row.extraction_method = extracted.extraction_method.value
            row.normalization_changed = extracted.normalization_changed
            row.validation_error = extracted.validation_error
            row.is_sensitive = row.is_sensitive or extracted.is_sensitive
            row.status = extracted.status
            row.candidates = [
                {
                    "raw_value": c.raw_value,
                    "normalized_value": c.normalized_value,
                    "pattern_id": c.pattern_id,
                    "confidence": c.confidence,
                    "page_number": c.page_number,
                    "pages": c.pages,
                    "validation_passed": c.validation_passed,
                }
                for c in extracted.candidates
            ]
        elif row.case_value:
            # Значение уже явно сохранено человеком в карточке заявителя.
            # Отсутствие такого значения в выписке не делает поле пустым.
            row.status = FieldStatus.confirmed
        elif row.default_value:
            # Значение по умолчанию — предложение, а не факт из документа.
            row.status = FieldStatus.needs_review

        # Решение специалиста окончательно: автоматические правила ниже
        # не должны его перебивать, иначе подтверждённое поле снова
        # покажется конфликтным и работа человека потеряется.
        if row.status not in _DECIDED_BY_SPECIALIST:
            # Расхождение реестра и карточки дела — конфликт.
            if (
                row.registry_value
                and row.case_value
                and row.registry_value != row.case_value
            ):
                row.status = FieldStatus.conflict
                row.validation_error = (
                    "Значение в карточке дела отличается от значения в выписке"
                )

            # Значения, собранные по правилу, подтверждаются всегда.
            if spec.get("always_needs_review") and row.status is FieldStatus.matched:
                row.status = FieldStatus.needs_review
                row.validation_error = row.validation_error or (
                    "Значение собрано из нескольких частей документа — "
                    "требуется проверка"
                )

            # Совпадающее значение в карточке означает, что пользователь
            # уже проверил и сохранил его. Не просим подтвердить то же самое
            # повторно на следующем экране.
            if (
                row.registry_value
                and row.case_value
                and row.registry_value == row.case_value
            ):
                row.status = FieldStatus.confirmed
                row.validation_error = None

        row.available_actions = self._actions_for(row)
        return row

    @staticmethod
    def _actions_for(row: MappingRow) -> list[str]:
        """Какие действия доступны специалисту по этому полю."""
        if row.status is FieldStatus.missing:
            # Принимать нечего — только ввести вручную или оставить пустым.
            actions = [ACTION_EDIT]
            if not row.required_for_application:
                actions.append(ACTION_LEAVE_EMPTY)
            return actions

        actions = [ACTION_ACCEPT, ACTION_EDIT, ACTION_REJECT]
        if not row.required_for_application:
            actions.append(ACTION_LEAVE_EMPTY)
        return actions

    # -- сводка -----------------------------------------------------------

    def summarise(self, rows: list[MappingRow]) -> dict[str, Any]:
        """Сводка по таблице сверки."""
        by_status: dict[str, int] = {}
        for row in rows:
            by_status[row.status.value] = by_status.get(row.status.value, 0) + 1

        blocking = [r for r in rows if r.blocks_document_generation]
        return {
            "mapping_version": self.version,
            "application_schema_version": self.config.get("application_schema_version"),
            "total": len(rows),
            "by_status": by_status,
            "requires_attention": sum(
                by_status.get(s, 0)
                for s in ("missing", "conflict", "needs_review")
            ),
            "blocking_document_generation": [r.label for r in blocking],
            "can_generate_draft": not blocking,
            "not_sourced_from_registry": self.config.get(
                "not_sourced_from_registry", []
            ),
        }


def build_reconciliation(
    extracted: Iterable[ExtractedFieldResult],
    case_values: dict[str, str] | None = None,
    mapping_name: str = "registry_to_application",
    client_type: str | None = None,
) -> tuple[list[MappingRow], dict[str, Any]]:
    """Удобная обёртка: извлечённые поля -> (таблица сверки, сводка)."""
    engine = FieldMappingEngine(mapping_name)
    rows = engine.build(extracted, case_values, client_type=client_type)
    return rows, engine.summarise(rows)
