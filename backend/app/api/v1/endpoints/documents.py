"""Загрузка, хранение и просмотр исходных документов дела.

Отличие от ``intake.py``: здесь файл действительно сохраняется, разбирается
постранично и связывается с делом. Все операции требуют авторизации.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.document_processing.classifier import classify_document
from app.infrastructure.database.models import (
    ApplicationStatus,
    AuditLog,
    DocumentKind,
    DocumentPage,
    DocumentProcessingStatus,
    ExtractionMethod,
    MarkType,
    OfficeActionResponse,
    SourceChannel,
    SourceDocument,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services import file_storage
from app.services.document_lifecycle import delete_document_and_release_blob
from app.services.document_text_extractor import (
    NoTextLayerError,
    UnsupportedDocumentType,
    extract_pages_from_bytes,
)
from app.services.mark_image import MarkImageError, process_mark_image

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])

# Роли, которым разрешено загружать и удалять документы.
_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}


class DocumentKindUpdate(BaseModel):
    """Явное решение человека о назначении загруженного файла."""

    document_kind: DocumentKind


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


def _has_application_access(user: User, application: TrademarkApplicationDraft) -> bool:
    return user.role is UserRole.admin or user.id in {
        application.created_by_user_id,
        application.assigned_lawyer_id,
        application.assigned_manager_id,
    }


def _require_application_access(user: User, application: TrademarkApplicationDraft) -> None:
    if not _has_application_access(user, application):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к документам заявки")


def _require_write_access(user: User, application: TrademarkApplicationDraft) -> None:
    if not _has_application_access(user, application) or (
        user.role not in _WRITE_ROLES and user.role is not UserRole.client
    ):
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


def _serialize_mark_image(
    document: SourceDocument, recognized_text: str = ""
) -> dict[str, Any]:
    metadata = document.metadata_json or {}
    return {
        "document_id": document.id,
        "application_id": document.application_id,
        "filename": document.original_filename,
        "file_size": document.file_size,
        "mime_type": document.detected_mime,
        "width": metadata.get("width"),
        "height": metadata.get("height"),
        "format": metadata.get("format"),
        "color_mode": metadata.get("color_mode"),
        "dominant_colors": metadata.get("dominant_colors") or [],
        "perceptual_hash": metadata.get("perceptual_hash"),
        "recognized_text": recognized_text,
        "ocr_confidence": metadata.get("ocr_confidence"),
        "ocr_warning": metadata.get("ocr_warning"),
        "visual_search_supported": False,
        "visual_search_notice": (
            "Система распознаёт слова на изображении и использует их в текстовом "
            "поиске. Автоматический поиск сходных изображений по реестру пока "
            "не выполняется."
        ),
    }


async def _active_mark_image(
    session: AsyncSession, application: TrademarkApplicationDraft
) -> SourceDocument | None:
    raw_id = application.mark_image_file_id
    if not raw_id or not str(raw_id).isdigit():
        return None
    result = await session.execute(
        select(SourceDocument).where(
            SourceDocument.id == int(raw_id),
            SourceDocument.application_id == application.id,
            SourceDocument.document_kind == DocumentKind.mark_image,
        )
    )
    return result.scalar_one_or_none()


async def _mark_image_text(session: AsyncSession, document_id: int) -> str:
    result = await session.execute(
        select(DocumentPage.text_content)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    return "\n".join(
        value.strip() for value in result.scalars() if value and value.strip()
    )


async def _supersede_current_mark_image(
    session: AsyncSession, application: TrademarkApplicationDraft
) -> None:
    current = await _active_mark_image(session, application)
    if current is None:
        return
    current.document_kind = DocumentKind.other
    metadata = dict(current.metadata_json or {})
    metadata["superseded_as_mark_image"] = True
    current.metadata_json = metadata


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

@router.post(
    "/applications/{application_id}/mark-image",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить изображение товарного знака",
)
async def upload_mark_image(
    application_id: int,
    file: UploadFile = File(..., description="Изображение PNG или JPEG"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Привязать изображение к обозначению и распознать словесные элементы."""
    application = await _load_application(session, application_id)
    _require_write_access(current_user, application)
    if application.mark_type not in {MarkType.figurative, MarkType.combined}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Изображение требуется для изобразительного или комбинированного "
                "знака. Сначала выберите соответствующий вид знака."
            ),
        )

    content = await file.read()
    filename = file_storage.normalize_upload_filename(file.filename or "mark.png")
    try:
        _, detected_mime = file_storage.validate_upload(content, filename)
        if detected_mime not in {"image/png", "image/jpeg"}:
            raise file_storage.FileValidationError(
                "Изображение обозначения должно быть в формате PNG или JPEG"
            )
        image = process_mark_image(content, filename)
        stored = file_storage.save_upload(content, filename)
    except (file_storage.FileValidationError, MarkImageError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _supersede_current_mark_image(session, application)
    metadata = image.metadata()
    metadata["ocr_confidence"] = image.ocr_confidence
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
        document_kind=DocumentKind.mark_image,
        kind_confidence=1.0,
        kind_requires_confirmation=False,
        processing_status=DocumentProcessingStatus.extracted,
        extraction_method=ExtractionMethod.ocr if image.recognized_text else None,
        page_count=1,
        char_count=len(image.recognized_text),
        metadata_json=metadata,
    )
    session.add(document)
    await session.flush()
    if image.recognized_text:
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=1,
                text_content=image.recognized_text,
                char_count=len(image.recognized_text),
                extraction_method=ExtractionMethod.ocr,
                ocr_confidence=image.ocr_confidence,
            )
        )
    application.mark_image_file_id = str(document.id)
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="mark_image.upload",
            entity_type="SourceDocument",
            entity_id=str(document.id),
            new_value_json={
                "sha256": stored.sha256,
                "width": image.width,
                "height": image.height,
                "ocr_text_found": bool(image.recognized_text),
            },
        )
    )
    await session.flush()
    return _serialize_mark_image(document, image.recognized_text)

@router.post(
    "/applications/{application_id}/source-documents",
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить документ в дело",
)
async def upload_document(
    application_id: int,
    file: UploadFile = File(..., description="PDF, DOCX, TXT, PNG, JPG, MP3 или WAV"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Проверить, сохранить и разобрать документ.

    Тип файла определяется по сигнатуре содержимого, а не по расширению.
    Текст извлекается постранично. Тип документа определяется правилами
    и в любом случае требует подтверждения специалистом.
    """
    application = await _load_application(session, application_id)
    _require_write_access(current_user, application)

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

    # Аудиозапись звукового знака хранится как оригинал: извлекать из неё текст
    # не нужно. Описание звучания заявитель подтверждает отдельным полем заявки.
    if stored.detected_mime in {"audio/mpeg", "audio/wav"}:
        document.document_kind = DocumentKind.mark_audio
        document.kind_confidence = 1.0
        document.kind_requires_confirmation = False
        document.processing_status = DocumentProcessingStatus.uploaded
        document.metadata_json = {"purpose": "sound_mark_recording"}
        session.add(
            AuditLog(
                user_id=current_user.id,
                application_id=application.id,
                action="mark_audio.upload",
                entity_type="SourceDocument",
                entity_id=str(document.id),
                new_value_json={"sha256": stored.sha256},
            )
        )
        await session.flush()
        return _serialize(document)

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
    "/applications/{application_id}/mark-image",
    summary="Получить сведения об изображении обозначения",
)
async def get_mark_image(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _load_application(session, application_id)
    _require_application_access(current_user, application)
    document = await _active_mark_image(session, application)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Изображение обозначения не загружено",
        )
    return _serialize_mark_image(
        document, await _mark_image_text(session, document.id)
    )


@router.get(
    "/applications/{application_id}/mark-image/content",
    summary="Показать изображение обозначения",
)
async def view_mark_image(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    application = await _load_application(session, application_id)
    _require_application_access(current_user, application)
    document = await _active_mark_image(session, application)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Изображение обозначения не загружено",
        )
    try:
        content = file_storage.read_file(document.stored_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл отсутствует в хранилище",
        ) from exc
    return Response(
        content=content,
        media_type=document.detected_mime or "application/octet-stream",
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/applications/{application_id}/mark-image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отвязать изображение обозначения",
)
async def delete_mark_image(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    application = await _load_application(session, application_id)
    _require_write_access(current_user, application)
    document = await _active_mark_image(session, application)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Изображение обозначения не загружено",
        )
    await _supersede_current_mark_image(session, application)
    application.mark_image_file_id = None
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="mark_image.detach",
            entity_type="SourceDocument",
            entity_id=str(document.id),
        )
    )
    await session.flush()

@router.get(
    "/applications/{application_id}/source-documents",
    summary="Список документов дела",
)
async def list_documents(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _load_application(session, application_id)
    _require_application_access(current_user, application)
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
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    document = await _load_document(session, document_id)
    application = await _load_application(session, document.application_id)
    _require_application_access(current_user, application)
    return _serialize(document)


@router.delete(
    "/source-documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить исходный документ и его извлечённые данные",
)
async def delete_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Physically remove an uploaded original when it is no longer needed.

    The audit trail deliberately keeps no filename, page text or extracted
    values: only the id, document kind and content hash remain as proof of the
    deletion operation.
    """

    document = await _load_document(session, document_id)
    application = await _load_application(session, document.application_id)
    _require_write_access(current_user, application)

    if application.status in {ApplicationStatus.submitted, ApplicationStatus.closed}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Документ относится к поданной или закрытой заявке. "
                "Для удаления обратитесь к администратору: сначала нужно "
                "проверить обязанность сохранить материалы дела."
            ),
        )

    used_in_response = await session.scalar(
        select(OfficeActionResponse.id).where(
            OfficeActionResponse.notice_document_id == document.id
        ).limit(1)
    )
    if used_in_response is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Документ используется в черновике ответа Роспатенту. "
                "Сначала удалите или замените связанный черновик."
            ),
        )

    if application.mark_image_file_id == str(document.id):
        application.mark_image_file_id = None

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="document.deleted",
            entity_type="SourceDocument",
            entity_id=str(document.id),
            old_value_json={
                "document_kind": document.document_kind.value,
                "sha256": document.sha256,
            },
        )
    )
    await delete_document_and_release_blob(session, document)


@router.put(
    "/source-documents/{document_id}/kind",
    summary="Подтвердить тип загруженного документа",
)
async def confirm_document_kind(
    document_id: int,
    payload: DocumentKindUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Сохранить назначение файла после решения пользователя или специалиста.

    Для изображений и сканов тип невозможно надёжно вывести из текста. Пока
    человек не подтвердил назначение, такой файл не должен автоматически
    становиться приложением к юридически значимой заявке.
    """
    if payload.document_kind in {
        DocumentKind.unknown,
        DocumentKind.unknown_registry_extract,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите конкретный тип документа",
        )
    document = await _load_document(session, document_id)
    application = await _load_application(session, document.application_id)
    _require_write_access(current_user, application)

    if payload.document_kind is DocumentKind.mark_image:
        if application.mark_type not in {MarkType.figurative, MarkType.combined}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Сначала выберите изобразительный или комбинированный вид знака"
                ),
            )
        if document.detected_mime not in {"image/png", "image/jpeg"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Изображение обозначения должно быть в формате PNG или JPEG",
            )
        await _supersede_current_mark_image(session, application)
        application.mark_image_file_id = str(document.id)
        try:
            content = file_storage.read_file(document.stored_path)
            image = process_mark_image(content, document.original_filename)
            metadata = dict(document.metadata_json or {})
            metadata.update(image.metadata())
            metadata["ocr_confidence"] = image.ocr_confidence
            document.metadata_json = metadata
            # Отсутствие текста не является ошибкой для графического знака.
            document.processing_status = DocumentProcessingStatus.extracted
            document.error_message = None
        except (FileNotFoundError, MarkImageError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
    elif application.mark_image_file_id == str(document.id):
        application.mark_image_file_id = None

    old_kind = document.document_kind.value
    document.document_kind = payload.document_kind
    document.kind_requires_confirmation = False
    metadata = dict(document.metadata_json or {})
    metadata["kind_confirmed_by_user_id"] = current_user.id
    document.metadata_json = metadata
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="document.kind_confirmed",
            entity_type="SourceDocument",
            entity_id=str(document.id),
            old_value_json={"document_kind": old_kind},
            new_value_json={"document_kind": payload.document_kind.value},
        )
    )
    await session.flush()
    return _serialize(document)


@router.get("/source-documents/{document_id}/pages", summary="Постраничный текст документа")
async def get_document_pages(
    document_id: int,
    page: Optional[int] = Query(default=None, ge=1, description="Только эта страница"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    document = await _load_document(session, document_id)
    application = await _load_application(session, document.application_id)
    _require_application_access(current_user, application)
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
    application = await _load_application(session, document.application_id)
    _require_application_access(current_user, application)
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
