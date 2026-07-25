"""Извлечение реквизитов из реестровых выписок (ЕГРЮЛ/ЕГРИП).

Принципы:
    1. Только детерминированная обработка: regex и правила. LLM здесь нет.
    2. Все паттерны привязаны к подписи поля — «голый» поиск цифр запрещён.
    3. Найдено несколько разных значений — сохраняются все, поле получает
       статус conflict. Молча брать первое нельзя.
    4. Одно и то же значение из разных паттернов — это подтверждение,
       а не конфликт: уверенность повышается.
    5. Ни одно значение не считается подтверждённым автоматически.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.document_processing.normalizers import compose_address, get_normalizer
from app.document_processing.validators import get_validator
from app.infrastructure.database.models import ExtractionMethod, FieldStatus

PATTERNS_DIR = Path(__file__).resolve().parents[1] / "patterns"

# Обрезка фрагмента-подтверждения: достаточно, чтобы специалист узнал
# место в документе, но не столько, чтобы тащить лишние персональные данные.
_SNIPPET_MAX = 200


# ---------------------------------------------------------------------------
# Результаты
# ---------------------------------------------------------------------------

@dataclass
class FieldCandidateResult:
    """Один вариант значения поля."""

    raw_value: str
    normalized_value: str
    pattern_id: str
    confidence: float
    page_number: int | None = None
    source_snippet: str = ""
    validation_passed: bool | None = None
    validation_error: str | None = None
    extraction_method: ExtractionMethod = ExtractionMethod.regex


@dataclass
class ExtractedFieldResult:
    """Итог по одному полю: значение, статус и все кандидаты."""

    field_id: str
    label: str
    status: FieldStatus
    required: bool = False
    is_sensitive: bool = False
    value: str | None = None
    normalized_value: str | None = None
    confidence: float | None = None
    page_number: int | None = None
    pattern_id: str | None = None
    source_snippet: str = ""
    validation_error: str | None = None
    normalization_changed: bool = False
    candidates: list[FieldCandidateResult] = field(default_factory=list)
    extraction_method: ExtractionMethod = ExtractionMethod.regex

    @property
    def needs_attention(self) -> bool:
        return self.status in (
            FieldStatus.conflict,
            FieldStatus.needs_review,
            FieldStatus.missing,
        )


# ---------------------------------------------------------------------------
# Текст с привязкой к страницам
# ---------------------------------------------------------------------------

@dataclass
class PagedText:
    """Склеенный текст документа с возможностью определить страницу."""

    text: str
    _page_starts: list[tuple[int, int]]  # (смещение начала, номер страницы)

    @classmethod
    def from_pages(cls, pages: Iterable[tuple[int, str]]) -> "PagedText":
        chunks: list[str] = []
        starts: list[tuple[int, int]] = []
        offset = 0
        for page_number, page_text in pages:
            starts.append((offset, page_number))
            chunks.append(page_text or "")
            offset += len(page_text or "") + 1  # +1 на разделитель
        return cls(text="\n".join(chunks), _page_starts=starts)

    def page_at(self, offset: int) -> int | None:
        """Определить номер страницы по смещению в склеенном тексте."""
        result = None
        for start, page_number in self._page_starts:
            if offset >= start:
                result = page_number
            else:
                break
        return result


# ---------------------------------------------------------------------------
# Конфигурация паттернов
# ---------------------------------------------------------------------------

# Конец значения в строке таблицы выписки. Значение может занимать
# несколько строк, поэтому граница описывается явно: следующая
# нумерованная строка, заголовок раздела или колонтитул страницы.
# Колонтитул обязателен: pdfplumber вставляет его прямо в середину
# таблицы, и без него захват «съедает» соседние строки.
ROW_END = (
    r"(?=\n\s*\d+\s+[А-ЯЁ]"
    r"|\nВыписка из ЕГР"
    r"|\nСтраница\s+\d"
    r"|\n\s*Сведения "
    r"|\n\s*Адрес \("
    r"|\n\s*Наименование\s*$"
    r"|\Z)"
)

# Плейсхолдеры, доступные в regex внутри YAML.
_PLACEHOLDERS = {"{ROW_END}": ROW_END}


def _expand(regex: str) -> str:
    for placeholder, replacement in _PLACEHOLDERS.items():
        regex = regex.replace(placeholder, replacement)
    return regex


@lru_cache(maxsize=8)
def load_pattern_config(document_kind: str) -> dict[str, Any]:
    """Загрузить YAML-конфигурацию паттернов для типа документа."""
    path = PATTERNS_DIR / f"{document_kind}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла паттернов для типа '{document_kind}': {path}"
        )
    with path.open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    for spec in config.get("fields", []):
        for pattern in spec.get("patterns", []):
            pattern["regex"] = _expand(pattern["regex"])
    return config


# ---------------------------------------------------------------------------
# Извлекатель
# ---------------------------------------------------------------------------

class RegistryExtractor:
    """Извлекает поля по YAML-конфигурации паттернов."""

    def __init__(self, document_kind: str = "egrul") -> None:
        self.config = load_pattern_config(document_kind)
        self.document_kind = document_kind

    # -- разделы ----------------------------------------------------------

    def _section_span(self, text: str, section_name: str) -> tuple[int, int] | None:
        """Границы раздела документа.

        Нужны, чтобы не спутать ФИО руководителя с ФИО учредителей:
        подписи полей у них идентичны.
        """
        sections = self.config.get("sections") or {}
        section = sections.get(section_name)
        if not section:
            return None

        start_match = re.search(section["start"], text, re.IGNORECASE)
        if not start_match:
            return None
        start = start_match.end()

        end = len(text)
        end_pattern = section.get("end")
        if end_pattern:
            end_match = re.search(end_pattern, text[start:], re.IGNORECASE)
            if end_match:
                end = start + end_match.start()
        return start, end

    # -- извлечение -------------------------------------------------------

    def extract(self, paged: PagedText) -> list[ExtractedFieldResult]:
        """Извлечь все поля, описанные в конфигурации."""
        results: list[ExtractedFieldResult] = []
        address_parts: dict[str, str] = {}
        address_pages: list[int] = []

        for spec in self.config.get("fields", []):
            result = self._extract_field(paged, spec)
            results.append(result)

            part = spec.get("address_part")
            if part and result.normalized_value:
                address_parts[part] = result.normalized_value
                if result.page_number:
                    address_pages.append(result.page_number)

        if address_parts:
            results.append(self._compose_address_field(address_parts, address_pages))

        return results

    def _extract_field(
        self, paged: PagedText, spec: dict[str, Any]
    ) -> ExtractedFieldResult:
        field_id = spec["field_id"]
        label = spec.get("label", field_id)
        required = bool(spec.get("required", False))
        sensitive = bool(spec.get("sensitive", False))

        # Ограничить поиск разделом, если он указан.
        search_text = paged.text
        base_offset = 0
        section_name = spec.get("section")
        if section_name:
            span = self._section_span(paged.text, section_name)
            if span is None:
                return ExtractedFieldResult(
                    field_id=field_id,
                    label=label,
                    required=required,
                    is_sensitive=sensitive,
                    status=FieldStatus.missing,
                    validation_error=f"Раздел '{section_name}' не найден в документе",
                )
            base_offset, end = span
            search_text = paged.text[base_offset:end]

        normalizer = get_normalizer(spec.get("normalizer"))
        validator = get_validator(spec.get("validator"))

        candidates: list[FieldCandidateResult] = []
        for pattern in spec.get("patterns", []):
            for match in re.finditer(pattern["regex"], search_text):
                raw = (match.group(1) if match.groups() else match.group(0)).strip()
                if not raw:
                    continue

                normalized = normalizer(raw)
                validation_passed: bool | None = None
                validation_error: str | None = None
                if validator is not None:
                    verdict = validator(normalized.value)
                    validation_passed = verdict.ok
                    validation_error = verdict.error

                absolute_offset = base_offset + match.start()
                snippet = search_text[
                    max(0, match.start() - 40) : match.end() + 40
                ].strip()

                candidates.append(
                    FieldCandidateResult(
                        raw_value=raw,
                        normalized_value=normalized.value,
                        pattern_id=pattern["pattern_id"],
                        confidence=float(pattern.get("confidence", 0.5)),
                        page_number=paged.page_at(absolute_offset),
                        source_snippet=re.sub(r"\s+", " ", snippet)[:_SNIPPET_MAX],
                        validation_passed=validation_passed,
                        validation_error=validation_error,
                    )
                )

        return self._resolve(
            field_id=field_id,
            label=label,
            required=required,
            sensitive=sensitive,
            candidates=candidates,
            normalizer_changed=self._normalization_changed(candidates, normalizer),
        )

    @staticmethod
    def _normalization_changed(
        candidates: list[FieldCandidateResult], normalizer
    ) -> bool:
        return any(c.raw_value != c.normalized_value for c in candidates)

    def _resolve(
        self,
        *,
        field_id: str,
        label: str,
        required: bool,
        sensitive: bool,
        candidates: list[FieldCandidateResult],
        normalizer_changed: bool,
    ) -> ExtractedFieldResult:
        """Свести кандидатов к одному результату со статусом."""
        base = ExtractedFieldResult(
            field_id=field_id,
            label=label,
            required=required,
            is_sensitive=sensitive,
            status=FieldStatus.missing,
            candidates=candidates,
            normalization_changed=normalizer_changed,
        )

        if not candidates:
            base.status = FieldStatus.missing
            if required:
                base.validation_error = "Обязательное поле не найдено в документе"
            return base

        # Одно и то же значение, найденное разными паттернами, —
        # подтверждение, а не конфликт.
        by_value: dict[str, list[FieldCandidateResult]] = {}
        for candidate in candidates:
            by_value.setdefault(candidate.normalized_value, []).append(candidate)

        # Значения, не прошедшие валидацию, не могут победить валидные.
        valid_values = {
            value
            for value, group in by_value.items()
            if any(c.validation_passed is not False for c in group)
        }
        contested = valid_values or set(by_value)

        if len(contested) > 1:
            # Разные значения — решение принимает специалист.
            best_value = max(
                contested,
                key=lambda v: max(c.confidence for c in by_value[v]),
            )
            best = max(by_value[best_value], key=lambda c: c.confidence)
            base.status = FieldStatus.conflict
            base.value = best.raw_value
            base.normalized_value = best.normalized_value
            base.confidence = best.confidence
            base.page_number = best.page_number
            base.pattern_id = best.pattern_id
            base.source_snippet = best.source_snippet
            base.validation_error = (
                f"Найдено {len(contested)} несовпадающих значений — "
                "требуется выбор специалиста"
            )
            return base

        value = next(iter(contested))
        group = by_value[value]
        best = max(group, key=lambda c: c.confidence)

        base.value = best.raw_value
        base.normalized_value = best.normalized_value
        base.page_number = best.page_number
        base.pattern_id = best.pattern_id
        base.source_snippet = best.source_snippet

        # Подтверждение несколькими независимыми паттернами повышает
        # уверенность, но никогда не доводит её до единицы.
        confidence = best.confidence
        if len({c.pattern_id for c in group}) > 1:
            confidence = min(0.98, confidence + 0.03)
        base.confidence = round(confidence, 2)

        failed = [c for c in group if c.validation_passed is False]
        if failed and len(failed) == len(group):
            base.status = FieldStatus.needs_review
            base.validation_error = failed[0].validation_error
        else:
            base.status = FieldStatus.matched

        return base

    def _compose_address_field(
        self, parts: dict[str, str], pages: list[int]
    ) -> ExtractedFieldResult:
        """Собрать адрес одной строкой из компонентов выписки."""
        composed = compose_address(parts)
        return ExtractedFieldResult(
            field_id="registry.legal_entity.address.full",
            label="Адрес места нахождения (собран из компонентов)",
            required=False,
            status=FieldStatus.needs_review if not composed.value else FieldStatus.matched,
            value=composed.original,
            normalized_value=composed.value,
            # Собранное значение всегда менее надёжно, чем прочитанное
            # целиком: порядок и состав компонентов задаются правилом.
            confidence=0.8,
            page_number=min(pages) if pages else None,
            pattern_id="composed_from_parts",
            source_snippet=composed.value[:_SNIPPET_MAX],
            normalization_changed=True,
            extraction_method=ExtractionMethod.rule,
        )


def extract_registry_fields(
    pages: Iterable[tuple[int, str]], document_kind: str = "egrul"
) -> list[ExtractedFieldResult]:
    """Удобная обёртка: страницы → список извлечённых полей."""
    extractor = RegistryExtractor(document_kind)
    return extractor.extract(PagedText.from_pages(pages))
