"""Bounded disposable parser processes; timeouts terminate OCR descendants too."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys

from app.core.config import settings
from app.services.document_text_extractor import ExtractedPage, NoTextLayerError
from app.services.mark_image import MarkImageError, MarkImageResult

_slot = asyncio.Semaphore(1)


async def _parse(content: bytes, filename: str, mode: str):
    from app.services.file_storage import validate_upload
    validate_upload(content, filename)
    # Bound waiting requests as well as execution; no unbounded work queue.
    try:
        await asyncio.wait_for(_slot.acquire(), timeout=1)
    except TimeoutError as exc:
        raise NoTextLayerError("Разбор занят. Повторите загрузку позже.") from exc
    process = None
    try:
        env = os.environ.copy()
        for key in ("OCR_ENABLED", "OCR_LANGUAGES", "OCR_DPI", "OCR_PSM",
                    "OCR_MIN_TEXT_CHARS", "OCR_TIMEOUT_SECONDS", "OCR_MAX_IMAGE_PIXELS",
                    "DOCUMENT_MAX_PAGES", "DOCUMENT_MAX_EXPANDED_MB",
                    "DOCUMENT_PARSE_TIMEOUT", "DOCUMENT_PARSE_MEMORY_MB"):
            env[key] = str(getattr(settings, key))
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.workers.parse_document", mode, filename,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=env,
            start_new_session=os.name != "nt",
        )
        output, _ = await asyncio.wait_for(
            process.communicate(content), timeout=settings.DOCUMENT_PARSE_TIMEOUT
        )
        if process.returncode:
            raise NoTextLayerError("Документ превысил лимиты разбора или повреждён")
        result = json.loads(output)
        if "error" in result:
            raise NoTextLayerError(result["error"])
        return result["result"]
    except TimeoutError as exc:
        raise NoTextLayerError("Превышено время разбора документа") from exc
    finally:
        if process is not None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.returncode is None:
                process.kill()
            await process.wait()
        _slot.release()


async def extract_pages(content: bytes, filename: str) -> list[ExtractedPage]:
    return [ExtractedPage(**page) for page in await _parse(content, filename, "pages")]


async def extract_text(content: bytes, filename: str) -> str:
    return "\n\n".join(page.text for page in await extract_pages(content, filename))


async def inspect_image(content: bytes, filename: str) -> MarkImageResult:
    try:
        return MarkImageResult(**await _parse(content, filename, "image"))
    except NoTextLayerError as exc:
        raise MarkImageError(str(exc)) from exc
