"""Проверка цитат: подтверждение, что модель не выдумала источник.

Смысл модуля. RAG нужен не только чтобы дать модели контекст, но и чтобы
можно было проверить каждый вывод. Слабая модель охотно сочиняет
правдоподобные ссылки на несуществующие пункты закона. Поэтому цитата
принимается только если её текст **действительно присутствует**
в выданном фрагменте базы знаний.

Точное совпадение слишком строго: модель нормализует пробелы, кавычки,
может обрезать окончание. Поэтому сравнение идёт по нормализованному
тексту, а частичное совпадение оценивается долей совпавших слов.

Вывод без подтверждённой цитаты не сохраняется и не показывается
специалисту как обоснованный.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# Доля слов цитаты, которая должна найтись в источнике, чтобы считать
# цитату подтверждённой при неточном совпадении.
PARTIAL_MATCH_THRESHOLD = 0.85

# Слишком короткая «цитата» ничего не подтверждает: два-три слова
# найдутся в любом тексте.
MIN_QUOTE_WORDS = 4


class CitationStatus(str, Enum):
    verified = "verified"           # текст найден в источнике
    partial = "partial"             # найдена большая часть слов
    not_found = "not_found"         # в источнике такого нет
    source_missing = "source_missing"  # указанного источника не существует
    too_short = "too_short"         # цитата слишком коротка для проверки


@dataclass(frozen=True)
class CitationCheck:
    status: CitationStatus
    source_id: str | None
    quote: str
    matched_ratio: float = 0.0
    anchor: str | None = None

    @property
    def is_trustworthy(self) -> bool:
        return self.status in (CitationStatus.verified, CitationStatus.partial)


def _normalize(text: str) -> str:
    """Привести текст к виду, устойчивому к косметическим различиям."""
    text = text.lower()
    text = text.replace("ё", "е")
    # Разные кавычки и тире — к единому виду.
    text = re.sub(r"[«»“”„‟\"']", " ", text)
    text = re.sub(r"[—–−-]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return _normalize(text).split()


def verify_quote(quote: str, source_text: str) -> tuple[CitationStatus, float]:
    """Проверить, присутствует ли цитата в тексте источника."""
    quote_words = _words(quote)
    if len(quote_words) < MIN_QUOTE_WORDS:
        return CitationStatus.too_short, 0.0

    normalized_source = _normalize(source_text)
    normalized_quote = " ".join(quote_words)

    if normalized_quote in normalized_source:
        return CitationStatus.verified, 1.0

    # Неточное совпадение: считаем долю слов цитаты, найденных
    # в источнике. Порядок не учитываем — модель могла переставить.
    source_words = set(normalized_source.split())
    matched = sum(1 for word in quote_words if word in source_words)
    ratio = matched / len(quote_words)

    if ratio >= PARTIAL_MATCH_THRESHOLD:
        return CitationStatus.partial, ratio
    return CitationStatus.not_found, ratio


def check_citation(
    quote: str,
    source_id: str | None,
    available_sources: dict[str, str],
    anchor: str | None = None,
) -> CitationCheck:
    """Проверить одну цитату против выданных моделью фрагментов.

    ``available_sources`` — только те фрагменты, которые были переданы
    модели в контексте. Ссылка на источник, которого модель не видела,
    заведомо недостоверна.
    """
    if not source_id or source_id not in available_sources:
        return CitationCheck(
            status=CitationStatus.source_missing,
            source_id=source_id,
            quote=quote,
            anchor=anchor,
        )

    status, ratio = verify_quote(quote, available_sources[source_id])
    return CitationCheck(
        status=status,
        source_id=source_id,
        quote=quote,
        matched_ratio=round(ratio, 3),
        anchor=anchor,
    )


@dataclass
class VerificationReport:
    """Итог проверки всех цитат одного вывода агента."""

    checks: list[CitationCheck]

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def verified(self) -> list[CitationCheck]:
        return [c for c in self.checks if c.is_trustworthy]

    @property
    def rejected(self) -> list[CitationCheck]:
        return [c for c in self.checks if not c.is_trustworthy]

    @property
    def has_any_trustworthy_source(self) -> bool:
        """Есть ли хотя бы одно подтверждённое основание.

        Если нет — вывод не может считаться обоснованным, каким бы
        убедительным ни выглядел текст.
        """
        return bool(self.verified)

    def summary(self) -> dict:
        return {
            "total": self.total,
            "verified": len(self.verified),
            "rejected": len(self.rejected),
            "rejected_reasons": [
                {
                    "quote": c.quote[:120],
                    "source_id": c.source_id,
                    "status": c.status.value,
                    "matched_ratio": c.matched_ratio,
                }
                for c in self.rejected
            ],
        }


def verify_all(
    citations: list[dict],
    available_sources: dict[str, str],
) -> VerificationReport:
    """Проверить список цитат из ответа модели.

    Каждая цитата — словарь с ключами ``quote``, ``source_id``
    и необязательным ``anchor``.
    """
    checks = [
        check_citation(
            quote=str(citation.get("quote", "")),
            source_id=citation.get("source_id"),
            available_sources=available_sources,
            anchor=citation.get("anchor"),
        )
        for citation in citations
    ]
    return VerificationReport(checks=checks)
