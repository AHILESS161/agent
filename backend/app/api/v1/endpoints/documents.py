"""Загрузка, хранение и просмотр исходных документов дела.

Отличие от ``intake.py``: здесь файл действительно сохраняется, разбирается
постранично и связывается с делом. Все операции требуют авторизации.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.document_processing.classifier import classify_document
from app.infrastructure.database.models import (
    AuditLog,
    DocumentPage,
    DocumentProcessingStatus,
    ExtractionMethod,
    SourceChannel,
    SourceDocument,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services import file_storage
from app.services.document_text_extractor import (
    NoTextLayerError,
    UnsupportedDocumentType,
    extract_pages_from_bytes,
)

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])

# Роли, которым разрешено загружать и удалять документы.
_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

async def _load_application(
    session: AsyncSession, application_id: int
) -> TrademarkApplicationDraft:
    result = await session.execute(
        select(TrademarkApplicationDraft).where(
            TrademarkApplicationDraft.id == application_id
        )
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Дело {application_id} не найдено",
        )
    return application


async def _load_document(session: AsyncSession, document_id: int) -> SourceDocument:
    result = await session.execute(
        select(SourceDocument).where(SourceDocument.id == document_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Документ {document_id} не найден",
        )
    return document


def _require_write_access(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения документов дела",
        )


def _serialize(document: SourceDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "application_id": document.application_id,
        "original_filename": document.original_filename,
        "file_size": document.file_size,
        "sha256": document.sha256,
        "detected_mime": document.detected_mime,
        "document_kind": document.document_kind.value,
        "kind_confidence": document.kind_confidence,
        "kind_requires_confirmation": document.kind_requires_confirmation,
        "processing_status": document.processing_status.value,
        "extraction_method": (
            document.extraction_method.value if document.extraction_method else None
        ),
        "page_count": document.page_count,
        "char_count": document.char_count,
        "error_message": document.error_message,
        "source_channel": document.source_channel.value,
        "uploaded_by_user_id": document.uploaded_by_user_id,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

@router.post(
    "/applications/{application_id}/source-documents",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить документ в дело",
)
async def upload_document(
    application_id: int,
    file: UploadFile = File(..., description="PDF, DOCX, TXT, PNG или JPG"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Проверить, сохранить и разобрать документ.

    Тип файла определяется по сигнатуре содержимого, а не по расширению.
    Текст извлекается постранично. Тип документа определяется правилами
    и в любом случае требует подтверждения специалистом.
    """
    _require_write_access(current_user)
    application = await _load_application(session, application_id)

    content = await file.read()
    filename = file_storage.normalize_upload_filename(file.filename or "upload")

    # --- проверка и сохранение оригинала ---
    try:
        stored = file_storage.save_upload(content, filename)
    except file_storage.FileValidationError as exc:
        logger.warning(
            "Загрузка отклонена",
            application_id=application_id,
            user_id=current_user.id,
            filename=filename,
            reason=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    document = SourceDocument(
        application_id=application.id,
        client_id=application.client_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        stored_path=stored.stored_path,
        declared_content_type=file.content_type,
        detected_mime=stored.detected_mime,
        file_size=stored.size,
        sha256=stored.sha256,
        source_channel=SourceChannel.manual_upload,
        processing_status=DocumentProcessingStatus.extracting,
    )
    session.add(document)
    await session.flush()

    # --- извлечение текста ---
    try:
        pages = extract_pages_from_bytes(content, filename)
    except (NoTextLayerError, UnsupportedDocumentType) as exc:
        reason = str(exc)
        pages = None
    except Exception as exc:  # noqa: BLE001
        # Повреждённый файл с корректной сигнатурой — реальный сценарий.
        # Он не должен ронять запрос: оригинал уже сохранён, специалист
        # разберёт его вручную.
        logger.warning(
            "Ошибка разбора документа",
            document_id=document.id,
            application_id=application_id,
            error=str(exc),
        )
        reason = f"Не удалось разобрать файл (возможно, он повреждён): {exc}"
        pages = None

    if pages is None:
        document.processing_status = DocumentProcessingStatus.failed
        document.error_message = reason
        await session.flush()
        logger.info(
            "Текст не извлечён",
            document_id=document.id,
            application_id=application_id,
            reason=reason,
        )
        return {**_serialize(document), "warning": reason}

    total_chars = 0
    for page in pages:
        total_chars += len(page.text)
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                text_content=page.text,
                char_count=len(page.text),
                extraction_method=ExtractionMethod(page.method),
                ocr_confidence=page.ocr_confidence,
            )
        )

    # --- определение типа ---
    full_text = "\n".join(p.text for p in pages)
    classification = classify_document(full_text)

    document.document_kind = classification.kind
    document.kind_confidence = classification.confidence
    document.kind_requires_confirmation = classification.requires_confirmation
    document.page_count = len(pages)
    document.char_count = total_chars
    document.extraction_method = (
        ExtractionMethod.ocr
        if any(page.method == ExtractionMethod.ocr.value for page in pages)
        else ExtractionMethod(pages[0].method)
    )
    document.processing_status = DocumentProcessingStatus.extracted
    document.metadata_json = {
        "classification_reason": classification.reason,
        "classification_markers": classification.matched_markers,
    }

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="document.upload",
            entity_type="SourceDocument",
            entity_id=str(document.id),
            # Имя файла и хэш — без содержимого и без персональных данных.
            new_value_json={
                "filename": filename,
                "sha256": stored.sha256,
                "kind": classification.kind.value,
            },
        )
    )
    await session.flush()

    logger.info(
        "Документ загружен",
        document_id=document.id,
        application_id=application_id,
        user_id=current_user.id,
        kind=classification.kind.value,
        pages=len(pages),
    )
    return _serialize(document)


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------

@router.get(
    "/applications/{application_id}/source-documents",
    summary="Список документов дела",
)
async def list_documents(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_application(session, application_id)
    result = await session.execute(
        select(SourceDocument)
        .where(SourceDocument.application_id == application_id)
        .order_by(SourceDocument.created_at.desc())
    )
    documents = list(result.scalars().all())
    return {"items": [_serialize(d) for d in documents], "total": len(documents)}


@router.get("/source-documents/{document_id}", summary="Карточка документа")
async def get_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    document = await _load_document(session, document_id)
    return _serialize(document)


@router.get("/source-documents/{document_id}/pages", summary="Постраничный текст документа")
async def get_document_pages(
    document_id: int,
    page: Optional[int] = Query(default=None, ge=1, description="Только эта страница"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_document(session, document_id)
    query = select(DocumentPage).where(DocumentPage.document_id == document_id)
    if page is not None:
        query = query.where(DocumentPage.page_number == page)
    result = await session.execute(query.order_by(DocumentPage.page_number))
    pages = list(result.scalars().all())
    return {
        "document_id": document_id,
        "items": [
            {
                "page_number": p.page_number,
                "text": p.text_content,
                "char_count": p.char_count,
                "extraction_method": p.extraction_method.value,
                "ocr_confidence": p.ocr_confidence,
            }
            for p in pages
        ],
        "total": len(pages),
    }


@router.get("/source-documents/{document_id}/download", summary="Скачать оригинал")
async def download_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Отдать оригинал файла.

    Файл читается по пути из БД, а не по пути из запроса — прямой доступ
    к хранилищу по URL невозможен.
    """
    document = await _load_document(session, document_id)
    try:
        content = file_storage.read_file(document.stored_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл отсутствует в хранилище",
        ) from exc

    logger.info(
        "Скачивание документа",
        document_id=document_id,
        user_id=current_user.id,
    )
    return Response(
        content=content,
        media_type=document.detected_mime or "application/octet-stream",
        headers={
            # filename* по RFC 5987 — корректно передаёт кириллицу в имени.
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{document.original_filename}"
            )
        },
    )
