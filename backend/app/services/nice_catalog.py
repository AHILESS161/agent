"""Справочник классов МКТУ для поиска.

Специалист подбирает класс не по номеру, а по смыслу: «одежда»,
«кофе», «разработка ПО». Поэтому нужен поиск по названию и составу
класса, а не поле ввода номера.

Источник — тот же файл базы знаний, что используется в RAG
(``knowledge/nice_classification_overview.md``): второго перечня
классов в системе быть не должно, иначе они разойдутся.

Поиск детерминированный: нормализация регистра и подстрочное
совпадение по названию и описанию. Языковая модель здесь не нужна —
это справочная выборка, а не семантический анализ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.infrastructure.rag.stemmer import stem

KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "knowledge"
    / "nice_classification_overview.md"
)

# «### Класс 25. Одежда и обувь»
_HEADING_RE = re.compile(r"^###\s*Класс\s+(\d+)\.\s*(.+?)\s*$", re.MULTILINE)

# Классы 1–34 — товары, 35–45 — услуги.
GOODS_MAX_CLASS = 34


@dataclass(frozen=True)
class NiceClass:
    number: int
    title: str
    description: str

    @property
    def kind(self) -> str:
        return "товары" if self.number <= GOODS_MAX_CLASS else "услуги"

    def as_dict(self) -> dict:
        return {
            "class_number": self.number,
            "title": self.title,
            "description": self.description,
            "kind": self.kind,
        }


@lru_cache(maxsize=1)
def load_catalog() -> tuple[NiceClass, ...]:
    """Разобрать перечень классов из базы знаний."""
    if not KNOWLEDGE_PATH.exists():
        return ()

    text = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    matches = list(_HEADING_RE.finditer(text))

    classes: list[NiceClass] = []
    for index, match in enumerate(matches):
        number = int(match.group(1))
        if not 1 <= number <= 45:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        # У последнего класса нет следующего заголовка, и без этой
        # границы в его описание попадал весь остаток файла — тогда
        # класс 45 находился по любому запросу.
        section = re.search(r"^##\s", text[start:end], re.MULTILINE)
        if section:
            end = start + section.start()

        body = " ".join(text[start:end].split())
        classes.append(
            NiceClass(number=number, title=match.group(2).strip(), description=body)
        )

    # Один и тот же класс не должен попасть дважды.
    unique: dict[int, NiceClass] = {}
    for item in classes:
        unique.setdefault(item.number, item)
    return tuple(sorted(unique.values(), key=lambda c: c.number))


def search(query: str = "", limit: int = 45) -> list[NiceClass]:
    """Найти классы по номеру, названию или составу.

    Пустой запрос возвращает весь перечень: специалисту бывает нужно
    просто просмотреть список.
    """
    catalog = load_catalog()
    normalized = (query or "").strip().lower()
    if not normalized:
        return list(catalog)[:limit]

    # Запрос числом — точное попадание по номеру класса.
    if normalized.isdigit():
        number = int(normalized)
        exact = [item for item in catalog if item.number == number]
        starts = [
            item
            for item in catalog
            if item not in exact and str(item.number).startswith(normalized)
        ]
        return (exact + starts)[:limit]

    # Запрос из нескольких слов ищется по каждому слову отдельно:
    # «разработка программ» не встречается в справочнике дословно,
    # но оба слова есть в описании класса 42. Слова приводятся к
    # основе тем же стеммером, что и в поиске по базе знаний, иначе
    # «производство одежды» не нашло бы класс «Одежда и обувь».
    query_stems = _stems(normalized)
    if not query_stems:
        return []

    # Требовать совпадения всех слов нельзя: в запросе вроде
    # «производство одежды» общее слово «производство» в описании
    # класса не встречается, и точное совпадение дало бы пусто.
    # Поэтому классы ранжируются по числу совпавших слов, а
    # совпадение в названии весит больше, чем в составе класса.
    scored: list[tuple[int, int, NiceClass]] = []
    for item in catalog:
        title_hits = len(query_stems & _title_stems(item))
        body_hits = len(query_stems & _full_stems(item))
        if not body_hits:
            continue
        scored.append((title_hits * 3 + body_hits, -item.number, item))

    scored.sort(key=lambda row: (-row[0], -row[1]))
    return [item for _, _, item in scored[:limit]]


def _stems(text: str) -> frozenset[str]:
    """Основы значимых слов текста."""
    return frozenset(
        stem(word)
        for word in re.split(r"\W+", text.lower())
        if len(word) >= 3
    )


@lru_cache(maxsize=64)
def _title_stems(item: NiceClass) -> frozenset[str]:
    return _stems(item.title)


@lru_cache(maxsize=64)
def _full_stems(item: NiceClass) -> frozenset[str]:
    return _stems(f"{item.title} {item.description}")
