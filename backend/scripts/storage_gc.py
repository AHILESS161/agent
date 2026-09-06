"""Offline document GC. Run only through deploy/maintenance.sh with writers stopped."""
from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import select
from app.infrastructure.database.models import SourceDocument
from app.infrastructure.database.session import AsyncSessionLocal, close_db
from app.services.file_storage import get_storage_root


async def collect(retention_days: int) -> int:
    async with AsyncSessionLocal() as session:
        referenced = set((await session.scalars(select(SourceDocument.stored_path))).all())
    cutoff = time.time() - retention_days * 86400
    root = get_storage_root()
    removed = 0
    for path in root.glob("*/*/*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in referenced and path.stat().st_mtime < cutoff:
            if path.resolve().is_relative_to(root):
                path.unlink()
                removed += 1
    await close_db()
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writers-stopped", action="store_true", required=True)
    parser.add_argument("--retention-days", type=int, default=7)
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("retention must be at least one day")
    print(f"Removed orphan blobs: {asyncio.run(collect(args.retention_days))}")
