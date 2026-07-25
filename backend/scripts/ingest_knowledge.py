"""Индексация базы знаний в БД.

Раньше индекс жил только в памяти процесса и терялся при перезапуске.
Скрипт сохраняет источники и фрагменты в таблицы ``knowledge_sources``
и ``knowledge_chunks`` с версионированием по хэшу содержимого:
неизменившийся документ повторно не переиндексируется.

Использование:
    python -m scripts.ingest_knowledge [--dir knowledge] [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402
from app.infrastructure.rag.store import (  # noqa: E402
    ingest_directory,
    knowledge_base_version,
    load_active_chunks,
)


async def main_async(directory: Path, show_chunks: bool) -> int:
    if not directory.exists():
        print(f"Каталог не найден: {directory}", file=sys.stderr)
        return 2

    async with AsyncSessionLocal() as session:
        results = await ingest_directory(session, directory)
        await session.commit()

        print("=" * 74)
        print(f"Каталог: {directory}")
        print("=" * 74)

        total_chunks = 0
        for result in results:
            state = "без изменений" if result.skipped_unchanged else "проиндексирован"
            print(
                f"  [{state:15}] {result.name[:44]:46} "
                f"фрагментов: {result.chunks_created:3}  версия: {result.version}"
            )
            total_chunks += result.chunks_created

        version = await knowledge_base_version(session)
        print("-" * 74)
        print(f"Источников: {len(results)}   фрагментов: {total_chunks}")
        print(f"Версия базы знаний: {version}")

        if show_chunks:
            print()
            print("Фрагменты с якорями:")
            for chunk in await load_active_chunks(session):
                preview = chunk.content[:60].replace("\n", " ")
                print(f"  {chunk.citation_id:8} [{chunk.anchor:20}] {preview}…")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Проиндексировать базу знаний")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "knowledge",
        help="Каталог с материалами (.md)",
    )
    parser.add_argument(
        "--show-chunks", action="store_true", help="Показать список фрагментов"
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.dir, args.show_chunks))


if __name__ == "__main__":
    raise SystemExit(main())
