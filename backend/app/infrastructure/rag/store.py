"""Персистентное хранение базы знаний.

Раньше индекс жил только в памяти процесса и терялся при перезапуске,
а таблицы ``knowledge_sources`` и ``knowledge_chunks`` не использовались.
Здесь источники и фрагменты сохраняются в БД: это даёт версионирование,
воспроизводимость выводов и возможность сослаться на конкретный фрагмент
из отчёта спустя время.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceType,
)
from app.infrastructure.rag.chunker import chunk_markdown

logger = get_logger(__name__)


@dataclass
class IngestResult:
    source_id: int
    name: str
    chunks_created: int
    version: str
    skipped_unchanged: bool = False


def _file_version(content: str) -> str:
    """Версия источника — хэш содержимого.

    Позволяет понять, изменился ли документ, и не переиндексировать
    его лишний раз.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


async def ingest_file(
    session: AsyncSession,
    path: Path,
    source_type: KnowledgeSourceType = KnowledgeSourceType.regulation,
    url: str | None = None,
) -> IngestResult:
    """Загрузить файл в базу знаний с разбиением на фрагменты."""
    content = path.read_text(encoding="utf-8")
    version = _file_version(content)

    existing = (
        await session.execute(
            select(KnowledgeSource).where(KnowledgeSource.file_path == str(path))
        )
    ).scalar_one_or_none()

    if existing and existing.version == version:
        chunk_count = len(
            (
                await session.execute(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.source_id == existing.id
                    )
                )
            ).scalars().all()
        )
        return IngestResult(
            source_id=existing.id,
            name=existing.name,
            chunks_created=chunk_count,
            version=version,
            skipped_unchanged=True,
        )

    # Первая строка Markdown-заголовка — название источника.
    title = next(
        (line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("# ")),
        path.stem,
    )

    if existing:
        # Документ изменился: старые фрагменты больше не соответствуют
        # содержимому и должны быть заменены целиком.
        for stale in (
            await session.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.source_id == existing.id)
            )
        ).scalars().all():
            await session.delete(stale)
        source = existing
        source.version = version
        source.name = title
        source.source_type = source_type
        source.is_active = True
    else:
        source = KnowledgeSource(
            name=title,
            source_type=source_type,
            file_path=str(path),
            url=url,
            version=version,
            is_active=True,
        )
        session.add(source)

    await session.flush()

    chunks = chunk_markdown(content)
    for chunk in chunks:
        session.add(
            KnowledgeChunk(
                source_id=source.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                metadata_json=chunk.to_metadata(),
            )
        )
    await session.flush()

    logger.info(
        "Источник знаний проиндексирован",
        source=title,
        chunks=len(chunks),
        version=version,
    )
    return IngestResult(
        source_id=source.id,
        name=title,
        chunks_created=len(chunks),
        version=version,
    )


# Соответствие файлов типам источников. Тип определяет, в какой анализ
# попадёт материал: нормы — в оценку оснований отказа, справочник МКТУ —
# в подбор классов.
_SOURCE_TYPE_BY_NAME: dict[str, KnowledgeSourceType] = {
    "gk_rf": KnowledgeSourceType.law,
    "nice_classification": KnowledgeSourceType.methodology,
    "rospatent_guidelines": KnowledgeSourceType.regulation,
}


def detect_source_type(path: Path) -> KnowledgeSourceType:
    stem = path.stem.lower()
    for prefix, source_type in _SOURCE_TYPE_BY_NAME.items():
        if stem.startswith(prefix):
            return source_type
    return KnowledgeSourceType.regulation


async def ingest_directory(
    session: AsyncSession,
    directory: Path,
    pattern: str = "*.md",
) -> list[IngestResult]:
    """Проиндексировать все документы каталога."""
    results = []
    for path in sorted(directory.glob(pattern)):
        results.append(await ingest_file(session, path, detect_source_type(path)))
    return results


@dataclass
class StoredChunk:
    """Фрагмент из БД, пригодный для передачи в контекст модели."""

    chunk_id: int
    source_id: int
    source_name: str
    source_version: str | None
    content: str
    anchor: str
    article: str | None
    clause: str | None
    # Тип источника: по нему анализы отбирают свой корпус. Нормы нужны
    # для оценки оснований отказа, справочник МКТУ — для подбора классов.
    source_type: str = "regulation"

    @property
    def citation_id(self) -> str:
        """Идентификатор, который модель обязана указать в цитате."""
        return f"kb-{self.chunk_id}"


async def load_active_chunks(session: AsyncSession) -> list[StoredChunk]:
    """Загрузить фрагменты активных источников."""
    rows = (
        await session.execute(
            select(KnowledgeChunk, KnowledgeSource)
            .join(KnowledgeSource, KnowledgeChunk.source_id == KnowledgeSource.id)
            .where(KnowledgeSource.is_active.is_(True))
            .order_by(KnowledgeChunk.source_id, KnowledgeChunk.chunk_index)
        )
    ).all()

    chunks: list[StoredChunk] = []
    for chunk, source in rows:
        meta = chunk.metadata_json or {}
        chunks.append(
            StoredChunk(
                chunk_id=chunk.id,
                source_id=source.id,
                source_name=source.name,
                source_version=source.version,
                source_type=source.source_type.value,
                content=chunk.content,
                anchor=meta.get("anchor") or "без раздела",
                article=meta.get("article"),
                clause=meta.get("clause"),
            )
        )
    return chunks


async def knowledge_base_version(session: AsyncSession) -> str:
    """Сводная версия базы знаний.

    Попадает в отчёт: по ней можно понять, на какой редакции
    материалов был сделан вывод.
    """
    sources = (
        await session.execute(
            select(KnowledgeSource)
            .where(KnowledgeSource.is_active.is_(True))
            .order_by(KnowledgeSource.id)
        )
    ).scalars().all()

    if not sources:
        return "empty"
    combined = "|".join(f"{s.id}:{s.version or '-'}" for s in sources)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
