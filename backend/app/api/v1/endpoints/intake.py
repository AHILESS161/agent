"""
Intake endpoints — загрузка и парсинг заполненной формы заявки Роспатента.

Поддерживает:
    POST /api/v1/intake/parse-application        — multipart с файлом
    POST /api/v1/intake/parse-application-text   — JSON с уже извлечённым текстом

Эти endpoint'ы НЕ создают заявку в БД. Они возвращают распарсенный dict,
который клиент использует для предзаполнения формы создания заявки.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.agents.intake.application_pdf_parser import ApplicationPdfParserAgent
from app.api.dependencies import _get_llm_provider, _get_prompt_registry
from app.core.security import get_current_user
from app.infrastructure.database.models import User
from app.services import file_storage
from app.schemas.intake import (
    ParseApplicationFromTextRequest,
    ParsedApplicationResponse,
)
from app.services.document_text_extractor import (
    UnsupportedDocumentType,
    extract_text_from_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intake", tags=["intake"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


async def _run_parser(raw_text: str, use_llm: bool) -> ParsedApplicationResponse:
    registry = _get_prompt_registry()
    llm = _get_llm_provider()
    agent = ApplicationPdfParserAgent(registry, llm)
    output = await agent.run({"raw_text": raw_text, "use_llm": use_llm})
    data = output.findings or {}
    # Агент кладёт полный результат в findings["parsed"]; разворачиваем.
    parsed = data.get("parsed") or data
    return ParsedApplicationResponse(
        client=parsed.get("client", {}),
        application=parsed.get("application", {}),
        representative=parsed.get("representative", {}),
        priority=parsed.get("priority", {}),
        confidence=parsed.get("confidence", {}),
        warnings=parsed.get("warnings", []),
        source_text_length=parsed.get("source_text_length", len(raw_text)),
        extraction_method=parsed.get("extraction_method", "heuristic+llm_fallback"),
    )


@router.post(
    "/parse-application",
    response_model=ParsedApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_application(
    file: UploadFile = File(..., description="PDF/DOCX заполненной заявки"),
    use_llm: bool = False,
    _current_user: User = Depends(get_current_user),
) -> ParsedApplicationResponse:
    """Парсит загруженный файл формы заявки (PDF или DOCX).

    Ничего не сохраняет — результат используется для предзаполнения формы.
    Для загрузки документа в дело есть ``POST /applications/{id}/documents``.

    ``use_llm`` по умолчанию выключен: сначала детерминированные правила,
    LLM — только явным запросом как fallback.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указано имя файла",
        )

    content = await file.read()
    # Тип проверяется по сигнатуре содержимого, а не по расширению.
    try:
        file_storage.validate_upload(content, file.filename)
    except file_storage.FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    t0 = time.perf_counter()
    try:
        raw_text = extract_text_from_bytes(content, file.filename)
    except UnsupportedDocumentType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Text extraction failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не удалось извлечь текст: {exc}",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не содержит извлекаемого текста (возможно, это скан без OCR)",
        )

    response = await _run_parser(raw_text, use_llm)
    response.source_filename = file.filename
    logger.info(
        "parse_application: file=%s chars=%d elapsed=%.2fs",
        file.filename,
        len(raw_text),
        time.perf_counter() - t0,
    )
    return response


@router.post(
    "/parse-application-text",
    response_model=ParsedApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_application_text(
    payload: ParseApplicationFromTextRequest,
    _current_user: User = Depends(get_current_user),
) -> ParsedApplicationResponse:
    """Парсит уже извлечённый текст формы (используется в тестах и в e2e)."""
    response = await _run_parser(payload.raw_text, payload.use_llm)
    response.source_filename = "<raw_text>"
    return response