"""Анализ бланка заявки на регистрацию товарного знака.

Строит машиночитаемую схему полей заявления, извлекая структуру
документа детерминированно: коды INID (ВОИС ST.9), подписи полей,
таблицы, чекбоксы и области для изображения. LLM не используется.

Оригинал документа не изменяется — он открывается только на чтение.

Использование:
    python -m scripts.analyze_application_template <путь-к-бланку> \
        [--out resources/application_templates/trademark_application.schema.json]

Про чекбоксы. В бланке Роспатента они нарисованы как векторные
прямоугольники, а не как символы, поэтому в текстовом слое отсутствуют
полностью. Их отмеченность из PDF надёжно определить нельзя, поэтому
все они попадают в схему с признаком manual_confirmation_required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber  # noqa: E402

SCHEMA_VERSION = "1.0.0"

# Геометрия чекбокса в бланке: квадрат со стороной ~6 пунктов.
_CHECKBOX_MIN = 4.0
_CHECKBOX_MAX = 15.0
_CHECKBOX_ASPECT_TOLERANCE = 0.35

# Насколько далеко вправо от квадрата искать подпись.
_LABEL_MAX_DISTANCE = 260
_LABEL_VERTICAL_TOLERANCE = 6

# Коды INID (ВОИС ST.9), встречающиеся в бланке, и их назначение.
INID_FIELDS: dict[str, dict[str, Any]] = {
    "210": {"label": "Регистрационный номер заявки", "field_id": "application.registration_number", "type": "string", "filled_by": "rospatent"},
    "220": {"label": "Дата подачи заявки", "field_id": "application.filing_date", "type": "date", "filled_by": "rospatent"},
    "750": {"label": "Адрес для переписки с Роспатентом", "field_id": "application.correspondence_address", "type": "text", "required": True},
    "731": {"label": "Заявитель", "field_id": "application.applicant.block", "type": "text", "required": True},
    "740": {"label": "Представитель заявителя", "field_id": "application.representative.block", "type": "text"},
    "540": {"label": "Заявляемое обозначение", "field_id": "application.mark.image", "type": "image", "required": True},
    "571": {"label": "Описание заявляемого обозначения", "field_id": "application.mark.description", "type": "text", "required": True},
    "591": {"label": "Цвет или цветовое сочетание", "field_id": "application.mark.colors", "type": "text"},
    "550": {"label": "Указание, относящееся к виду знака", "field_id": "application.mark.kind", "type": "choice", "required": True},
    "551": {"label": "Коллективный знак", "field_id": "application.mark.is_collective", "type": "boolean"},
    "554": {"label": "Объёмный знак", "field_id": "application.mark.is_volumetric", "type": "boolean"},
    "555": {"label": "Голографический знак", "field_id": "application.mark.is_holographic", "type": "boolean"},
    "556": {"label": "Звуковой знак", "field_id": "application.mark.is_sound", "type": "boolean"},
    "557": {"label": "Обонятельный знак", "field_id": "application.mark.is_olfactory", "type": "boolean"},
    "558": {"label": "Знак из одного или нескольких цветов", "field_id": "application.mark.is_colour_only", "type": "boolean"},
    "526": {"label": "Неохраняемые элементы", "field_id": "application.mark.disclaimed_elements", "type": "text"},
    "511": {"label": "Перечень товаров и услуг по классам МКТУ", "field_id": "application.goods_services", "type": "table", "required": True},
    "320": {"label": "Дата подачи первой заявки (конвенционный приоритет)", "field_id": "application.priority.first_filing_date", "type": "date"},
    "330": {"label": "Код страны подачи первой заявки", "field_id": "application.priority.country_code", "type": "string"},
    "310": {"label": "Номер первой заявки", "field_id": "application.priority.first_application_number", "type": "string"},
    "230": {"label": "Дата начала показа экспоната на выставке", "field_id": "application.priority.exhibition_date", "type": "date"},
    "641": {"label": "Номер первоначальной заявки (выделенная заявка)", "field_id": "application.priority.parent_application_number", "type": "string"},
    "151": {"label": "Номер международной регистрации", "field_id": "application.priority.international_registration_number", "type": "string"},
    "646": {"label": "Территориальное расширение по международной регистрации", "field_id": "application.priority.territorial_extension", "type": "string"},
}

# Подполя блока (731). В бланке это один свободный блок, куда вписывают
# наименование и адрес подряд, но в карточке дела и при генерации
# документа они нужны раздельно.
BLOCK_SUBFIELDS: list[dict[str, Any]] = [
    {
        "field_id": "application.applicant.name",
        "label": "Полное наименование заявителя (или ФИО ИП)",
        "parent_inid": "731",
        "type": "string",
        "required": True,
        "normalizer": "legal_entity_name",
    },
    {
        "field_id": "application.applicant.address",
        "label": "Полный адрес места нахождения заявителя",
        "parent_inid": "731",
        "type": "text",
        "required": True,
        "normalizer": "whitespace",
    },
    {
        "field_id": "application.representative.name",
        "label": "ФИО представителя заявителя",
        "parent_inid": "740",
        "type": "string",
        "required": False,
        "sensitive": True,
        "normalizer": "person_name",
    },
]

# Поля-идентификаторы заявителя, размеченные подписями, а не кодами INID.
LABELLED_FIELDS: list[dict[str, Any]] = [
    {"field_id": "application.applicant.ogrn", "label": "ОГРН заявителя", "anchor": r"ОГРН:", "type": "string", "validator": "ogrn"},
    {"field_id": "application.applicant.ogrnip", "label": "ОГРНИП заявителя", "anchor": r"ОГРНИП:", "type": "string", "validator": "ogrnip"},
    {"field_id": "application.applicant.inn", "label": "ИНН заявителя", "anchor": r"ИНН \(при наличии\):", "type": "string", "validator": "inn"},
    {"field_id": "application.applicant.kpp", "label": "КПП заявителя", "anchor": r"КПП \(при наличии\):", "type": "string", "validator": "kpp"},
    {"field_id": "application.applicant.country_code", "label": "Код страны по стандарту ВОИС ST.3", "anchor": r"ВОИС ST\.3", "type": "string"},
    {"field_id": "application.representative.registration_number", "label": "Регистрационный номер патентного поверенного", "anchor": r"Регистрационный номер", "type": "string"},
    {"field_id": "application.signature.name", "label": "ФИО подписавшего", "anchor": r"^Подпись", "type": "string", "required": True, "sensitive": True},
]


def _is_checkbox(rect: dict[str, Any]) -> bool:
    width = rect["x1"] - rect["x0"]
    height = abs(rect["bottom"] - rect["top"])
    if not (_CHECKBOX_MIN < width < _CHECKBOX_MAX):
        return False
    if not (_CHECKBOX_MIN < height < _CHECKBOX_MAX):
        return False
    # Квадрат, а не полоска таблицы.
    return abs(width - height) <= _CHECKBOX_ASPECT_TOLERANCE * max(width, height)


def _label_for_checkbox(
    rect: dict[str, Any],
    words: list[dict[str, Any]],
    siblings: list[dict[str, Any]],
) -> str:
    """Подпись чекбокса — текст справа от квадрата до следующего квадрата.

    Ограничение по соседнему чекбоксу обязательно: в бланке на одной
    строке стоит до четырёх вариантов подряд, и без границы подпись
    первого поглощает подписи всех остальных.
    """
    centre = (rect["top"] + rect["bottom"]) / 2

    # Ближайший чекбокс правее на той же строке задаёт правую границу.
    right_bound = rect["x1"] + _LABEL_MAX_DISTANCE
    for other in siblings:
        if other is rect or other["x0"] <= rect["x1"]:
            continue
        if abs((other["top"] + other["bottom"]) / 2 - centre) > _LABEL_VERTICAL_TOLERANCE:
            continue
        right_bound = min(right_bound, other["x0"])

    candidates = [
        word
        for word in words
        if word["x0"] >= rect["x1"] - 1
        and word["x1"] <= right_bound + 1
        and abs((word["top"] + word["bottom"]) / 2 - centre) <= _LABEL_VERTICAL_TOLERANCE
    ]
    candidates.sort(key=lambda w: w["x0"])

    label = re.sub(r"\s+", " ", " ".join(w["text"] for w in candidates)).strip()
    # Ведущий код INID относится к группе полей, а не к самому варианту.
    label = re.sub(r"^\(\d{3}\)\s*", "", label)
    return label


def analyse(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()

    fields: list[dict[str, Any]] = []
    checkboxes: list[dict[str, Any]] = []
    tables_found: list[dict[str, Any]] = []
    unresolved: list[str] = []
    page_texts: list[str] = []

    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)

        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_texts.append(text)
            words = page.extract_words()

            # --- чекбоксы ---
            page_checkboxes = [rect for rect in page.rects if _is_checkbox(rect)]
            for rect in page_checkboxes:
                label = _label_for_checkbox(rect, words, page_checkboxes)
                checkboxes.append(
                    {
                        "page": page_index,
                        "position": {
                            "x": round(rect["x0"], 1),
                            "y": round(rect["top"], 1),
                            "width": round(rect["x1"] - rect["x0"], 1),
                            "height": round(abs(rect["bottom"] - rect["top"]), 1),
                        },
                        "label": label or None,
                        # Заливка/обводка сохраняются как наблюдение, но
                        # состояние по ним НЕ выводится: в бланке отметка
                        # может быть проставлена вне векторного слоя.
                        "observed_fill": bool(rect.get("fill")),
                        "state": "undetermined",
                        "manual_confirmation_required": True,
                    }
                )
                if not label:
                    unresolved.append(
                        f"Чекбокс на стр. {page_index} "
                        f"(x={rect['x0']:.0f}, y={rect['top']:.0f}) без распознанной подписи"
                    )

            # --- таблицы ---
            for table_index, table in enumerate(page.find_tables()):
                tables_found.append(
                    {
                        "page": page_index,
                        "table_index": table_index,
                        "rows": len(table.rows),
                        "columns": len(table.columns),
                        "bbox": [round(v, 1) for v in table.bbox],
                    }
                )

    full_text = "\n".join(page_texts)

    # --- поля по кодам INID ---
    for code, spec in INID_FIELDS.items():
        match = re.search(rf"\({code}\)", full_text)
        page_number = None
        if match:
            offset = 0
            for index, text in enumerate(page_texts, start=1):
                if offset <= match.start() < offset + len(text) + 1:
                    page_number = index
                    break
                offset += len(text) + 1
        else:
            unresolved.append(f"Код INID ({code}) не найден в бланке")

        fields.append(
            {
                "field_id": spec["field_id"],
                "label": spec["label"],
                "section": "Бланк заявки",
                "inid_code": code,
                "data_type": spec["type"],
                "required": bool(spec.get("required", False)),
                "filled_by": spec.get("filled_by", "applicant"),
                "found_in_template": match is not None,
                "source_document_position": {"page": page_number},
                "validation": {"regex": None, "normalizer": None},
                # Значения типа choice/boolean соответствуют чекбоксам.
                "manual_confirmation_required": spec["type"] in ("choice", "boolean", "image"),
            }
        )

    # --- подполя блоков INID ---
    for spec in BLOCK_SUBFIELDS:
        parent_present = f"({spec['parent_inid']})" in full_text
        if not parent_present:
            unresolved.append(
                f"Родительский блок ({spec['parent_inid']}) не найден "
                f"для поля {spec['field_id']}"
            )
        fields.append(
            {
                "field_id": spec["field_id"],
                "label": spec["label"],
                "section": "Бланк заявки",
                "inid_code": spec["parent_inid"],
                "is_subfield_of_block": True,
                "data_type": spec["type"],
                "required": bool(spec.get("required", False)),
                "sensitive": bool(spec.get("sensitive", False)),
                "filled_by": "applicant",
                "found_in_template": parent_present,
                "source_document_position": {"page": None},
                "validation": {
                    "regex": None,
                    "normalizer": spec.get("normalizer"),
                },
                "manual_confirmation_required": False,
            }
        )

    # --- поля по текстовым подписям ---
    for spec in LABELLED_FIELDS:
        match = re.search(spec["anchor"], full_text, re.MULTILINE)
        if not match:
            unresolved.append(f"Подпись поля не найдена: {spec['label']}")
        fields.append(
            {
                "field_id": spec["field_id"],
                "label": spec["label"],
                "section": "Бланк заявки",
                "inid_code": None,
                "data_type": spec["type"],
                "required": bool(spec.get("required", False)),
                "sensitive": bool(spec.get("sensitive", False)),
                "filled_by": "applicant",
                "found_in_template": match is not None,
                "source_document_position": {"page": None},
                "validation": {
                    "regex": None,
                    "validator": spec.get("validator"),
                    "normalizer": None,
                },
                "manual_confirmation_required": False,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "template_name": "Заявка на государственную регистрацию товарного знака",
        "source": {
            "filename": path.name,
            "sha256": sha256,
            "file_size": len(content),
            "format": "pdf",
            "page_count": page_count,
            "has_text_layer": bool(full_text.strip()),
        },
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "analysis_method": "deterministic (pdfplumber: text, rects, tables). LLM не использовался.",
        "limitations": [
            "Чекбоксы бланка нарисованы векторными прямоугольниками и "
            "отсутствуют в текстовом слое; их отмеченность из PDF надёжно "
            "не определяется. Все поля вида choice/boolean требуют ручного "
            "подтверждения специалистом.",
            "Область (540) «Заявляемое обозначение» содержит изображение, "
            "а не текст: значение подтверждается вручную.",
            "Позиции полей приведены с точностью до страницы; координаты "
            "сохранены только для чекбоксов.",
        ],
        "statistics": {
            "fields_total": len(fields),
            "fields_found_in_template": sum(1 for f in fields if f["found_in_template"]),
            "fields_requiring_manual_confirmation": sum(
                1 for f in fields if f.get("manual_confirmation_required")
            ),
            "checkboxes_detected": len(checkboxes),
            "checkboxes_without_label": sum(1 for c in checkboxes if not c["label"]),
            "tables_detected": len(tables_found),
        },
        "fields": fields,
        "checkboxes": checkboxes,
        "tables": tables_found,
        "unresolved": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Построить схему полей заявления из бланка (без LLM)"
    )
    parser.add_argument("path", type=Path, help="PDF бланка заявки")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("resources/application_templates/trademark_application.schema.json"),
        help="Куда сохранить схему",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Файл не найден: {args.path}", file=sys.stderr)
        return 2

    schema = analyse(args.path)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stats = schema["statistics"]
    print("=" * 78)
    print(f"Бланк:    {schema['source']['filename']}")
    print(f"SHA-256:  {schema['source']['sha256']}")
    print(f"Страниц:  {schema['source']['page_count']}   версия схемы: {schema['schema_version']}")
    print("=" * 78)
    print(f"Полей описано:            {stats['fields_total']}")
    print(f"  найдено в бланке:       {stats['fields_found_in_template']}")
    print(f"  требуют подтверждения:  {stats['fields_requiring_manual_confirmation']}")
    print(f"Чекбоксов обнаружено:     {stats['checkboxes_detected']}")
    print(f"  без подписи:            {stats['checkboxes_without_label']}")
    print(f"Таблиц обнаружено:        {stats['tables_detected']}")

    if schema["unresolved"]:
        print()
        print(f"Не распознано ({len(schema['unresolved'])}):")
        for item in schema["unresolved"][:15]:
            print(f"  - {item}")
        if len(schema["unresolved"]) > 15:
            print(f"  … ещё {len(schema['unresolved']) - 15}")

    print()
    print(f"Схема сохранена: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
