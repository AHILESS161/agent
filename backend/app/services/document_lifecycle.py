"""Safe lifecycle operations for uploaded source documents.

Database rows and content-addressed files have different lifecycles. A single
blob may be referenced by more than one ``SourceDocument`` row, so deleting a
case must not blindly unlink every stored path.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import SourceDocument
from app.services import file_storage


async def delete_document_and_release_blob(
    session: AsyncSession,
    document: SourceDocument,
) -> bool:
    """Delete a document row and unlink its blob when no other row uses it."""

    stored_path = document.stored_path
    await session.delete(document)
    await session.flush()
    return await release_unreferenced_blob(session, stored_path)


async def release_unreferenced_blob(
    session: AsyncSession,
    stored_path: str,
) -> bool:
    """Defer physical deletion to offline GC after committed references are checked.

    Unlinking here can lose a document on rollback or race an uncommitted upload.
    The maintenance GC runs with API and worker stopped, with a retention period.
    """

    remaining = await session.scalar(
        select(func.count(SourceDocument.id)).where(
            SourceDocument.stored_path == stored_path
        )
    )
    if remaining:
        return False
    return False


async def release_unreferenced_blobs(
    session: AsyncSession,
    stored_paths: Iterable[str],
) -> int:
    """Release a de-duplicated collection of blobs and return removal count."""

    removed = 0
    for stored_path in set(stored_paths):
        removed += int(await release_unreferenced_blob(session, stored_path))
    return removed
