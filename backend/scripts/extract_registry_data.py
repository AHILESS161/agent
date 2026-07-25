"""Извлечение реквизитов из реестровой выписки (ЕГРЮЛ/ЕГРИП).

Детерминированно: regex и правила, без обращения к LLM.
Оригинал документа не изменяется.

Использование:
    python -m scripts.extract_registry_data <путь-к-файлу> [--json out.json]
                                            [--show-snippets] [--unmask]

По умолчанию персональные данные (ФИО руководителя) маскируются в выводе.
Флаг --unmask показывает их полностью — использовать осознанно.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Пакет app лежит на уровень выше каталога scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.document_processing.classifier import classify_document  # noqa: E402
from app.document_processing.extractors import extract_registry_fields  # noqa: E402
from app.infrastructure.database.models import DocumentKind, FieldStatus  # noqa: E402
from app.services.document_text_extractor import (  # noqa: E402
    NoTextLayerError,
    extract_pages_from_bytes,
)

# Какие типы документов умеет обрабатывать этот скрипт.
_SUPPORTED = {
    DocumentKind.egrul_extract: "egrul",
    DocumentKind.unknown_registry_extract: "egrul",
}

_STATUS_LABEL = {
    FieldStatus.matched: "OK      ",
    FieldStatus.conflict: "КОНФЛИКТ",
    FieldStatus.needs_review: "ПРОВЕРКА",
    FieldStatus.missing: "НЕ НАЙД.",
}


def _mask(value: str | None) -> str:
    """Замаскировать персональные данные для вывода в консоль и логи."""
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Извлечь реквизиты из реестровой выписки (без LLM)"
    )
    parser.add_argument("path", type=Path, help="PDF/DOCX/TXT выписки")
    parser.add_argument("--json", type=Path, help="Сохранить результат в JSON")
    parser.add_argument(
        "--show-snippets", action="store_true", help="Показать фрагменты-источники"
    )
    parser.add_argument(
        "--unmask",
        action="store_true",
        help="Не маскировать персональные данные в выводе",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Файл не найден: {args.path}", file=sys.stderr)
        return 2

    content = args.path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()

    # --- текст ---
    try:
        pages = extract_pages_from_bytes(content, args.path.name)
    except NoTextLayerError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 3

    full_text = "\n".join(p.text for p in pages)

    # --- тип документа ---
    classification = classify_document(full_text)
    print("=" * 78)
    print(f"Файл:        {args.path.name}")
    print(f"SHA-256:     {sha256}")
    print(f"Страниц:     {len(pages)}   символов: {len(full_text)}")
    print(f"Тип:         {classification.kind.value} (уверенность {classification.confidence})")
    print(f"Обоснование: {classification.reason}")
    print("=" * 78)

    if classification.kind not in _SUPPORTED:
        print(
            f"\nТип '{classification.kind.value}' не поддерживается этим скриптом.\n"
            "Требуется ручное подтверждение типа документа.",
            file=sys.stderr,
        )
        return 4

    if classification.kind is DocumentKind.unknown_registry_extract:
        print(
            "\nВНИМАНИЕ: тип выписки не определён уверенно. "
            "Результат обязательно требует проверки специалистом.\n"
        )

    # --- извлечение ---
    results = extract_registry_fields([(p.page_number, p.text) for p in pages])

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status.value] = counts.get(result.status.value, 0) + 1

    print()
    for result in results:
        value = result.normalized_value or ""
        if result.is_sensitive and not args.unmask:
            value = _mask(value)
        label = _STATUS_LABEL.get(result.status, result.status.value)
        page = f"стр.{result.page_number}" if result.page_number else "стр.-"
        confidence = f"{result.confidence:.2f}" if result.confidence else " -  "
        print(f"[{label}] {result.field_id:46} {page:8} {confidence}  {value}")

        if result.validation_error:
            print(f"{'':11} ! {result.validation_error}")
        if len(result.candidates) > 1:
            distinct = {c.normalized_value for c in result.candidates}
            if len(distinct) > 1:
                print(f"{'':11} кандидаты: {sorted(distinct)}")
        if args.show_snippets and result.source_snippet:
            print(f"{'':11} источник: …{result.source_snippet[:110]}…")

    # --- сводка ---
    print()
    print("-" * 78)
    total = len(results)
    matched = counts.get("matched", 0)
    print(
        f"Итого: {matched}/{total} извлечено | "
        + " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    )
    print("Метод извлечения: regex/rules. LLM не использовался.")
    print(
        "Ни одно значение не считается подтверждённым: требуется "
        "проверка специалистом."
    )
    print("-" * 78)

    # --- JSON ---
    if args.json:
        payload = {
            "source": {
                "filename": args.path.name,
                "sha256": sha256,
                "page_count": len(pages),
                "char_count": len(full_text),
                "extraction_method": pages[0].method if pages else None,
            },
            "classification": {
                "kind": classification.kind.value,
                "confidence": classification.confidence,
                "requires_confirmation": classification.requires_confirmation,
                "reason": classification.reason,
            },
            "analysed_at": datetime.now(timezone.utc).isoformat(),
            "fields": [
                {
                    "field_id": r.field_id,
                    "label": r.label,
                    "status": r.status.value,
                    "required": r.required,
                    "is_sensitive": r.is_sensitive,
                    "raw_value": r.value,
                    "normalized_value": r.normalized_value,
                    "confidence": r.confidence,
                    "page_number": r.page_number,
                    "pattern_id": r.pattern_id,
                    "extraction_method": r.extraction_method.value,
                    "validation_error": r.validation_error,
                    "normalization_changed": r.normalization_changed,
                    "source_snippet": r.source_snippet,
                    "candidates": [
                        {
                            "raw_value": c.raw_value,
                            "normalized_value": c.normalized_value,
                            "pattern_id": c.pattern_id,
                            "confidence": c.confidence,
                            "page_number": c.page_number,
                            "validation_passed": c.validation_passed,
                            "validation_error": c.validation_error,
                        }
                        for c in r.candidates
                    ],
                }
                for r in results
            ],
        }
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON сохранён: {args.json}")

    # Ненулевой код, если есть поля, требующие внимания.
    needs_attention = sum(
        counts.get(s, 0) for s in ("conflict", "needs_review", "missing")
    )
    return 1 if needs_attention else 0


if __name__ == "__main__":
    raise SystemExit(main())
