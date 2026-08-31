"""Сформировать обезличенные DOCX-образцы для ручной юридической приёмки.

Скрипт не создаёт дела в базе и не использует пользовательские документы.
Он строит шесть воспроизводимых образцов официального заявления: для
юридического лица, ИП и физического лица, по словесному и комбинированному
обозначению. Результаты предназначены только для сверки в Word/PDF по
``docs/legal-docx-review-checklist.md``.

Запуск из каталога ``backend``::

    python -m scripts.generate_docx_review_samples --out ../.review/docx
"""

from __future__ import annotations

import argparse
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

# Импорт генератора загружает общую конфигурацию приложения. Локальный .env не
# должен мешать автономной подготовке обезличенных образцов: скрипту не нужны
# debug-режим, БД или внешние интеграции.
os.environ["DEBUG"] = "false"

from app.infrastructure.database.models import MarkType
from app.services.application_draft import DraftContent, FilledField, render_docx
from app.services.nice_catalog import load_catalog


@dataclass
class _ReviewApplication:
    id: int
    mark_text: str
    mark_name: str
    mark_type: MarkType
    filing_method: str = "electronic"
    request_paper_certificate: bool = False
    signatory_name: str | None = None
    signatory_position: str | None = None
    signature_date = None


def _field(field_id: str, label: str, value: str) -> FilledField:
    return FilledField(
        field_id=field_id,
        label=label,
        value=value,
        source="обезличенный сценарий юридической приёмки",
    )


def _applicant_fields(applicant_type: str) -> list[FilledField]:
    common = [
        _field("application.applicant.country_code", "Код страны", "RU"),
        _field(
            "application.correspondence_address",
            "Адрес для переписки",
            "123456, г. Тестоград, ул. Проверочная, д. 10",
        ),
        _field("application.contact.phone", "Телефон", "+7 900 000-00-00"),
        _field("application.contact.email", "E-mail", "review@example.test"),
    ]
    if applicant_type == "company":
        return [
            _field(
                "application.applicant.name",
                "Заявитель",
                "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ПРИМЕР»",
            ),
            _field(
                "application.applicant.address",
                "Адрес",
                "123456, г. Тестоград, ул. Проверочная, д. 10",
            ),
            _field("application.applicant.ogrn", "ОГРН", "1027700000000"),
            _field("application.applicant.inn", "ИНН", "7700000000"),
            _field("application.applicant.kpp", "КПП", "770001001"),
            *common,
        ]
    if applicant_type == "sole_proprietor":
        return [
            _field("application.applicant.name", "Заявитель", "Иванов Иван Иванович"),
            _field(
                "application.applicant.address",
                "Адрес",
                "123456, г. Тестоград, ул. Проверочная, д. 11",
            ),
            _field("application.applicant.ogrnip", "ОГРНИП", "304770000000000"),
            _field("application.applicant.inn", "ИНН", "770000000000"),
            *common,
        ]
    return [
        _field("application.applicant.name", "Заявитель", "Петрова Анна Сергеевна"),
        _field(
            "application.applicant.address",
            "Адрес",
            "123456, г. Тестоград, ул. Проверочная, д. 12",
        ),
        _field("application.applicant.inn", "ИНН", "770000000001"),
        *common,
    ]


def _mark_image() -> bytes:
    """Нейтральное тестовое изображение без заимствованных материалов."""
    image = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (80, 100, 820, 500), radius=72, fill="#e8f8f6", outline="#109c98", width=16
    )
    draw.ellipse((125, 175, 325, 375), fill="#109c98")
    draw.rectangle((335, 255, 735, 295), fill="#101044")
    payload = io.BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _content(applicant_type: str, *, combined: bool) -> DraftContent:
    signatory_name = {
        "company": "Сидоров Сергей Сергеевич",
        "sole_proprietor": "Иванов Иван Иванович",
        "individual": "Петрова Анна Сергеевна",
    }[applicant_type]
    signatory_position = "Генеральный директор" if applicant_type == "company" else ""
    fields = [
        *_applicant_fields(applicant_type),
        _field("application.mark.text", "Обозначение", "ПРИМЕР ЗНАКА"),
        _field("application.signatory.name", "ФИО подписанта", signatory_name),
    ]
    if signatory_position:
        fields.append(
            _field("application.signatory.position", "Должность", signatory_position)
        )
    if combined:
        fields.extend(
            [
                _field(
                    "application.mark.description",
                    "Описание",
                    "Комбинированное обозначение состоит из геометрических элементов "
                    "бирюзового и тёмно-синего цветов, объединённых в единую композицию.",
                ),
                _field(
                    "application.mark.colors",
                    "Цветовое сочетание",
                    "бирюзовый, синий",
                ),
            ]
        )
    class_42 = next(item for item in load_catalog() if item.number == 42)
    return DraftContent(
        applicant_type=applicant_type,
        filled=fields,
        classes=[
            (
                "42",
                class_42.full_description,
            )
        ],
    )


def generate(output_dir: Path) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    image = _mark_image()
    index = 1
    for applicant_type in ("company", "sole_proprietor", "individual"):
        for mark_kind in ("word", "combined"):
            combined = mark_kind == "combined"
            application = _ReviewApplication(
                id=index,
                mark_text="ПРИМЕР ЗНАКА",
                mark_name="ПРИМЕР ЗНАКА",
                mark_type=MarkType.combined if combined else MarkType.word,
                signatory_name={
                    "company": "Сидоров Сергей Сергеевич",
                    "sole_proprietor": "Иванов Иван Иванович",
                    "individual": "Петрова Анна Сергеевна",
                }[applicant_type],
                signatory_position=(
                    "Генеральный директор" if applicant_type == "company" else None
                ),
            )
            filename = f"{index:02d}_{applicant_type}_{mark_kind}.docx"
            payload = render_docx(
                _content(applicant_type, combined=combined),
                application,
                mark_image=image if combined else None,
            )
            (output_dir / filename).write_bytes(payload)
            manifest.append(
                {
                    "file": filename,
                    "applicant_type": applicant_type,
                    "mark_type": mark_kind,
                    "review_checklist": "docs/legal-docx-review-checklist.md",
                }
            )
            index += 1
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../.review/docx"),
        help="Каталог для DOCX и manifest.json",
    )
    args = parser.parse_args()
    manifest = generate(args.out.resolve())
    print(f"Сформировано образцов: {len(manifest)}")
    print(args.out.resolve())


if __name__ == "__main__":
    main()
