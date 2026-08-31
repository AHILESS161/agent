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

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.infrastructure.rag.stemmer import stem

LEGACY_KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "knowledge"
    / "nice_classification_overview.md"
)
CURRENT_KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[1].parent
    / "knowledge"
    / "nice_classification_13_2026.md"
)

# «### Класс 25. Одежда и обувь»
_HEADING_RE = re.compile(r"^###\s*Класс\s+(\d+)\.\s*(.+?)\s*$", re.MULTILINE)

# Классы 1–34 — товары, 35–45 — услуги.
GOODS_MAX_CLASS = 34
_GENERIC_ACTIVITY_STEMS = frozenset(
    {stem("производство"), stem("изготовление"), stem("услуги")}
)

# У официального перечня и бытового запроса иногда оказываются разные основы:
# Snowball приводит «косметологические» к «косметологическ», а
# «косметологов» — к «косметолог». Добавляем только узкие предметные основы,
# чтобы не превращать поиск по справочнику в неточное совпадение по подстроке.
_DOMAIN_PREFIX_STEMS = {
    "косметолог": "косметолог",
}


@dataclass(frozen=True)
class NiceClass:
    number: int
    title: str
    description: str
    search_terms: str = ""
    items: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        return "товары" if self.number <= GOODS_MAX_CLASS else "услуги"

    def as_dict(self) -> dict:
        return {
            "class_number": self.number,
            "title": self.title,
            "description": self.description,
            "kind": self.kind,
            "item_count": len(self.items),
        }

    @property
    def full_description(self) -> str:
        """Полный официальный перечень позиций класса для заявления."""
        return "; ".join(self.items) if self.items else self.description


@lru_cache(maxsize=1)
def load_catalog() -> tuple[NiceClass, ...]:
    """Разобрать перечень классов из базы знаний."""
    knowledge_path = (
        CURRENT_KNOWLEDGE_PATH
        if CURRENT_KNOWLEDGE_PATH.exists()
        else LEGACY_KNOWLEDGE_PATH
    )
    if not knowledge_path.exists():
        return ()

    text = knowledge_path.read_text(encoding="utf-8")
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

        raw_body = text[start:end]
        body = " ".join(raw_body.split())
        # В актуальном снимке после заголовка идёт полный официальный перечень.
        # API отдаёт пользователю компактное описание, а поиск учитывает весь
        # перечень — иначе запросы вроде «смартфон» или «цепочка для кошелька»
        # теряются.
        official_heading = re.search(
            r"Официальный заголовок класса:\s*(.+?)(?:\n|$)",
            text[start:end],
        )
        description = official_heading.group(1).strip() if official_heading else body
        title = description if official_heading else match.group(2).strip()
        items = tuple(
            value.strip()
            for value in re.findall(
                r"^-\s*\d{6}\s*—\s*(.+?)\s*$",
                raw_body,
                flags=re.MULTILINE,
            )
            if value.strip()
        )
        classes.append(
            NiceClass(
                number=number,
                title=title,
                description=description,
                search_terms=body,
                items=items,
            )
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
    if len(query_stems) > 1:
        query_stems = query_stems - _GENERIC_ACTIVITY_STEMS
    if not query_stems:
        return []

    # Требовать совпадения всех слов нельзя: в запросе вроде
    # «производство одежды» общее слово «производство» в описании
    # класса не встречается, и точное совпадение дало бы пусто.
    # Поэтому классы ранжируются по числу совпавших слов, а
    # совпадение в названии весит больше, чем в составе класса.
    documents = [_full_stems(item) for item in catalog]
    document_frequency = {
        token: sum(token in document for document in documents)
        for token in query_stems
    }
    weights = {
        token: math.log((len(catalog) + 1) / (document_frequency[token] + 1)) + 1
        for token in query_stems
    }

    scored: list[tuple[float, int, NiceClass]] = []
    preferred_class = (
        44 if "косметолог" in normalized and "услуг" in normalized else None
    )
    for item in catalog:
        title_stems = _title_stems(item)
        full_stems = _full_stems(item)
        matched = query_stems & full_stems
        if not matched:
            continue
        score = sum(weights[token] for token in matched)
        score += 4 * sum(weights[token] for token in query_stems & title_stems)
        first_title_word = next(
            (word for word in re.split(r"\W+", item.title.lower()) if len(word) >= 3),
            "",
        )
        if first_title_word and stem(first_title_word) in query_stems:
            score += 8
        title_lower = item.title.lower().replace("ё", "е")
        if normalized in title_lower:
            score += 4
        if title_lower.startswith(normalized):
            score += 8
        if item.number == preferred_class:
            score += 50
        scored.append((score, -item.number, item))

    scored.sort(key=lambda row: (-row[0], -row[1]))
    return [item for _, _, item in scored[:limit]]


def _stems(text: str) -> frozenset[str]:
    """Основы значимых слов текста."""
    result: set[str] = set()
    for word in re.split(r"\W+", text.lower().replace("ё", "е")):
        if len(word) < 3:
            continue
        result.add(stem(word))
        for prefix, canonical in _DOMAIN_PREFIX_STEMS.items():
            if word.startswith(prefix):
                result.add(canonical)
    return frozenset(result)


@lru_cache(maxsize=64)
def _title_stems(item: NiceClass) -> frozenset[str]:
    return _stems(item.title)


@lru_cache(maxsize=64)
def _full_stems(item: NiceClass) -> frozenset[str]:
    return _stems(f"{item.title} {item.description} {item.search_terms}")
