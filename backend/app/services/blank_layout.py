"""Разметка бланка заявки для интерактивного просмотра.

Специалист должен видеть заявление в том виде, в каком оно уйдёт
в Роспатент: те же разделы, тот же порядок, те же коды INID. Поэтому
структура описана декларативно и повторяет официальную форму, а не
придумывает собственный вид.

Значения подставляются только подтверждённые. Поле, у которого
источника нет в принципе (вид знака, приоритет, пошлина), помечается
как заполняемое вручную — это свойство самой формы, а не ограничение
системы, и специалист должен видеть разницу.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.services.application_draft import DraftContent

LAYOUT_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "resources"
    / "application_templates"
    / "blank_layout.yaml"
)

# Как заполняется поле.
FILL_AUTO = "auto"  # из подтверждённых данных дела
FILL_MANUAL = "manual"  # источника нет, вносит специалист
FILL_CHECKBOX = "checkbox"  # отметка в бланке, только вручную
FILL_CLASSES = "classes"  # таблица классов МКТУ
FILL_OFFICE = "office"  # заполняет Роспатент


@dataclass
class LayoutField:
    inid: str | None
    label: str
    source: str | None
    fill: str
    value: str | None = None
    hint: str | None = None
    multiline: bool = False

    # --- сведения из сверки: откуда значение и что с ним делать ---
    status: str | None = None
    required: bool = False
    origin: str | None = None
    page_number: int | None = None
    is_sensitive: bool = False
    validation_error: str | None = None
    extracted_field_id: int | None = None
    field_path: str | None = None
    candidates: list[dict[str, Any]] = dc_field(default_factory=list)
    actions: list[str] = dc_field(default_factory=list)

    @property
    def is_filled(self) -> bool:
        return bool(self.value)

    @property
    def needs_attention(self) -> bool:
        """Обязательное поле без подтверждённого значения."""
        return self.required and self.status != "confirmed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "inid": self.inid,
            "label": self.label,
            "source": self.source,
            "fill": self.fill,
            "value": self.value,
            "hint": self.hint,
            "multiline": self.multiline,
            "is_filled": self.is_filled,
            "status": self.status,
            "required": self.required,
            "needs_attention": self.needs_attention,
            "origin": self.origin,
            "page_number": self.page_number,
            "is_sensitive": self.is_sensitive,
            "validation_error": self.validation_error,
            "extracted_field_id": self.extracted_field_id,
            "field_path": self.field_path,
            "candidates": self.candidates,
            "actions": self.actions,
            # Править можно всё, кроме того, что заполняет Роспатент.
            "editable": self.fill != FILL_OFFICE,
        }


@dataclass
class LayoutSection:
    id: str
    title: str
    readonly: bool = False
    fields: list[LayoutField] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "readonly": self.readonly,
            "fields": [f.as_dict() for f in self.fields],
            "filled_count": sum(1 for f in self.fields if f.is_filled),
            "total_count": len(self.fields),
        }


@lru_cache(maxsize=1)
def load_layout() -> dict[str, Any]:
    if not LAYOUT_PATH.exists():
        raise FileNotFoundError(f"Разметка бланка не найдена: {LAYOUT_PATH}")
    with LAYOUT_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# Как называть источник значения для специалиста.
_ORIGIN_LABELS = {
    "manual": "введено вручную",
    "pdf_text_layer": "из документа",
    "docx_parser": "из документа",
    "regex": "из документа",
    "ocr": "распознано с изображения",
}


def build_form(
    content: DraftContent,
    rows: list[Any] | None = None,
    client_type: str | None = None,
) -> dict[str, Any]:
    """Собрать бланк с подставленными значениями дела.

    ``rows`` — строки сверки полей. С ними бланк показывает не только
    итоговое значение, но и откуда оно взялось и что с ним делать:
    отдельная вкладка сверки для этого больше не нужна.

    Набор полей зависит от типа заявителя: у юрлица ОГРН и КПП,
    у предпринимателя ОГРНИП, у физлица — паспорт. Строки сверки уже
    отобраны по типу, поэтому неприменимые поля бланка скрываются,
    а сведения, которых в бланке нет (паспорт, руководитель), выводятся
    отдельным блоком: заполнять их всё равно нужно.
    """
    layout = load_layout()
    values = {item.field_id: item.value for item in content.filled}
    value_sources = {item.field_id: item.source for item in content.filled}

    # Строка сверки ищется по полю заявления, на которое она отображается.
    by_application_field = {
        row.application_field: row for row in (rows or []) if row.application_field
    }

    sections: list[LayoutSection] = []
    for raw_section in layout.get("sections", []):
        section = LayoutSection(
            id=raw_section["id"],
            title=raw_section["title"],
            readonly=bool(raw_section.get("readonly", False)),
        )
        for raw in raw_section.get("fields", []):
            fill = raw.get("fill", FILL_AUTO)
            source = raw.get("source")

            if fill == FILL_CLASSES:
                # Перечень товаров — таблица, а не одно значение.
                value = (
                    "; ".join(
                        f"Класс {number}: {goods}" if goods else f"Класс {number}"
                        for number, goods in content.classes
                    )
                    or None
                )
            else:
                value = values.get(source) if source else None

            layout_field = LayoutField(
                inid=str(raw["inid"]) if raw.get("inid") else None,
                label=raw["label"],
                source=source,
                fill=fill,
                value=value,
                hint=raw.get("hint"),
                multiline=bool(raw.get("multiline", False)),
            )

            # Даже если поле пришло не из загруженного документа, интерфейс
            # должен честно показать происхождение: карточка дела,
            # подтверждённые классы или другое правило предзаполнения.
            if source and value:
                layout_field.origin = value_sources.get(source)
            if fill == FILL_CLASSES and value:
                layout_field.origin = "подтверждённые классы МКТУ"

            row = by_application_field.get(source) if source else None

            # Поле заявителя, для которого у этого типа нет источника,
            # не показывается: у физлица не бывает ОГРН, у юрлица —
            # паспорта. Иначе бланк выглядел бы недозаполненным.
            if (
                row is None
                and fill == FILL_AUTO
                and raw_section["id"] == "applicant"
                and client_type is not None
            ):
                continue

            if row is not None:
                # Подпись берётся из сверки: у ИП то же поле бланка
                # называется «ФИО предпринимателя», а не «наименование».
                layout_field.label = row.label
                layout_field.status = row.status.value
                layout_field.required = row.required_for_application
                layout_field.page_number = row.page_number
                layout_field.is_sensitive = row.is_sensitive
                layout_field.validation_error = row.validation_error
                layout_field.candidates = row.candidates
                layout_field.actions = row.available_actions
                layout_field.field_path = row.registry_field or row.case_field
                layout_field.origin = _ORIGIN_LABELS.get(
                    row.extraction_method or "", row.extraction_method
                )
                # Значение из сверки показывается и до подтверждения:
                # специалист должен видеть, что предлагает система.
                if not layout_field.value and row.registry_value:
                    layout_field.value = row.registry_value

            section.fields.append(layout_field)
        sections.append(section)

    # Сведения, для которых в бланке отдельного поля нет: паспортные
    # данные физлица, руководитель юрлица. В заявление они не идут,
    # но нужны в деле — и заполнять их больше негде.
    extra = [
        row
        for row in (rows or [])
        if not row.application_field and row.case_field != "case.applicant.country_code"
    ]
    if extra:
        section = LayoutSection(
            id="case_only",
            title="Сведения дела (в бланк не переносятся)",
        )
        for row in extra:
            section.fields.append(
                LayoutField(
                    inid=None,
                    label=row.label,
                    source=row.case_field,
                    fill=FILL_MANUAL,
                    value=row.registry_value,
                    hint=row.note,
                    status=row.status.value,
                    required=row.required_for_application,
                    is_sensitive=row.is_sensitive,
                    validation_error=row.validation_error,
                    candidates=row.candidates,
                    actions=row.available_actions,
                    field_path=row.registry_field or row.case_field,
                    page_number=row.page_number,
                    origin=_ORIGIN_LABELS.get(
                        row.extraction_method or "", row.extraction_method
                    ),
                )
            )
        sections.append(section)

    all_fields = [f for section in sections for f in section.fields]
    total = len(all_fields)
    filled = sum(1 for f in all_fields if f.is_filled)
    required = [f for f in all_fields if f.required]
    blocking = [f for f in all_fields if f.needs_attention]

    return {
        "title": layout.get("title", "ЗАЯВКА"),
        "layout_version": layout.get("version"),
        "sections": [s.as_dict() for s in sections],
        "filled_count": filled,
        "total_count": total,
        "required_count": len(required),
        "required_done": len(required) - len(blocking),
        # Пока эти поля не подтверждены, заявление подавать нельзя.
        "blocking": [f.label for f in blocking],
        "can_generate": not blocking,
        "notice": (
            "Поля с пометкой «Заполняет специалист» требуют ручного действия. "
            "Для остальных полей рядом указан источник или ответственный."
        ),
    }
