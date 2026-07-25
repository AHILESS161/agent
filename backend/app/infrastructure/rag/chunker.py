"""Разбиение нормативных текстов на фрагменты с сохранением структуры.

Обычное разбиение по числу символов рвёт норму посреди предложения,
и потом невозможно сказать, из какой статьи взята цитата. Здесь границы
проходят по заголовкам Markdown, а каждый фрагмент помнит свой путь
в иерархии — «Статья 1483 → Пункт 1». Этот путь становится якорем
цитаты и позволяет специалисту проверить вывод по первоисточнику.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# Заголовок Markdown: уровень + текст.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# Номер статьи и пункта — вытаскиваются отдельно, чтобы по ним
# можно было фильтровать выдачу.
_ARTICLE_RE = re.compile(r"Стать[яи]\s+(\d+(?:\.\d+)?)")
_CLAUSE_RE = re.compile(r"Пункт\s+(\d+)")

DEFAULT_MAX_CHARS = 1500
DEFAULT_MIN_CHARS = 120


@dataclass
class Chunk:
    """Фрагмент базы знаний с якорем для цитирования."""

    content: str
    chunk_index: int
    # Путь в иерархии заголовков, напр. ["ГК РФ Часть IV", "Статья 1483", "Пункт 1"]
    heading_path: list[str] = field(default_factory=list)
    article: str | None = None
    clause: str | None = None
    # Порядковый номер части, если фрагмент пришлось делить по длине.
    part: int = 1
    parts_total: int = 1

    @property
    def anchor(self) -> str:
        """Человекочитаемая ссылка на место в источнике."""
        if self.article and self.clause:
            return f"ст. {self.article}, п. {self.clause}"
        if self.article:
            return f"ст. {self.article}"
        return " → ".join(self.heading_path[-2:]) if self.heading_path else "без раздела"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_metadata(self) -> dict:
        return {
            "heading_path": self.heading_path,
            "anchor": self.anchor,
            "article": self.article,
            "clause": self.clause,
            "part": self.part,
            "parts_total": self.parts_total,
            "content_hash": self.content_hash,
        }


def _split_long_section(text: str, max_chars: int) -> list[str]:
    """Разделить длинный раздел по абзацам, не разрывая предложения."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= max_chars:
            buffer = candidate
            continue

        if buffer:
            parts.append(buffer)
        # Абзац сам длиннее лимита — режем по предложениям.
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            buffer = ""
            for sentence in sentences:
                candidate = f"{buffer} {sentence}".strip()
                if len(candidate) <= max_chars:
                    buffer = candidate
                else:
                    if buffer:
                        parts.append(buffer)
                    buffer = sentence
        else:
            buffer = paragraph

    if buffer:
        parts.append(buffer)
    return parts or [text]


def chunk_markdown(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[Chunk]:
    """Разбить Markdown на фрагменты по заголовкам.

    Слишком короткие разделы (одни заголовки без содержания) отбрасываются:
    они не несут смысла и только зашумляют выдачу.
    """
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return _chunks_from_section(text, [], 0, max_chars, min_chars)

    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []  # (уровень, заголовок)

    for index, heading in enumerate(headings):
        level = len(heading.group(1))
        title = heading.group(2).strip()

        # Поднимаемся по иерархии до текущего уровня.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        if not body:
            continue

        path = [title for _, title in stack]
        chunks.extend(
            _chunks_from_section(body, path, len(chunks), max_chars, min_chars)
        )

    return chunks


def _chunks_from_section(
    body: str,
    heading_path: list[str],
    start_index: int,
    max_chars: int,
    min_chars: int,
) -> list[Chunk]:
    if len(body) < min_chars:
        return []

    joined = " ".join(heading_path)
    article_match = _ARTICLE_RE.search(joined)
    clause_match = _CLAUSE_RE.search(joined)

    parts = (
        _split_long_section(body, max_chars) if len(body) > max_chars else [body]
    )

    return [
        Chunk(
            content=part,
            chunk_index=start_index + offset,
            heading_path=list(heading_path),
            article=article_match.group(1) if article_match else None,
            clause=clause_match.group(1) if clause_match else None,
            part=offset + 1,
            parts_total=len(parts),
        )
        for offset, part in enumerate(parts)
    ]
