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

    @property
    def is_filled(self) -> bool:
        return bool(self.value)

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


def build_form(content: DraftContent) -> dict[str, Any]:
    """Собрать бланк с подставленными значениями дела."""
    layout = load_layout()
    values = {item.field_id: item.value for item in content.filled}

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

            section.fields.append(
                LayoutField(
                    inid=str(raw["inid"]) if raw.get("inid") else None,
                    label=raw["label"],
                    source=source,
                    fill=fill,
                    value=value,
                    hint=raw.get("hint"),
                    multiline=bool(raw.get("multiline", False)),
                )
            )
        sections.append(section)

    total = sum(len(s.fields) for s in sections)
    filled = sum(1 for s in sections for f in s.fields if f.is_filled)

    return {
        "title": layout.get("title", "ЗАЯВКА"),
        "layout_version": layout.get("version"),
        "sections": [s.as_dict() for s in sections],
        "filled_count": filled,
        "total_count": total,
        "notice": (
            "Пустые поля заполняются специалистом. Значения подставляются "
            "только после подтверждения на вкладке «Сверка полей»."
        ),
    }
