"""Приём обращений от клиентов.

Пока нет интеграции с CRM и почтой, обращение вносит юрист. Канал
``manual_upload`` проходит тот же путь, что будущие ``crm``, ``email``
и ``webhook``: событие сохраняется, вложения проходят проверку и
разбор, из обращения создаётся дело-черновик.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.document_processing.classifier import classify_document
from app.infrastructure.database.models import (
    AuditLog,
    DocumentPage,
    DocumentProcessingStatus,
    ExtractionMethod,
    InboundEvent,
    InboundStatus,
    MarkType,
    SourceChannel,
    SourceDocument,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services import file_storage, inbound
from app.services.document_text_extractor import (
    NoTextLayerError,
    UnsupportedDocumentType,
    extract_pages_from_bytes,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/inbound", tags=["inbound"])

_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}


class NewClientData(BaseModel):
    type: str = "company"
    full_name_or_company_name: str = Field(min_length=2, max_length=512)
    short_name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    inn: Optional[str] = None
    ogrn_or_ogrnip: Optional[str] = None
    kpp: Optional[str] = None
    country: Optional[str] = "RU"


class IntakeRequest(BaseModel):
    """Обращение, внесённое юристом."""

    sender: Optional[str] = Field(default=None, max_length=512)
    subject: Optional[str] = Field(default=None, max_length=512)
    body_text: Optional[str] = Field(default=None, max_length=20000)
    links: list[str] = Field(default_factory=list)
    external_event_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    # Куда направить обращение.
    target_case_id: Optional[int] = None
    create_case: bool = True

    # Данные для нового дела.
    client_id: Optional[int] = None
    new_client: Optional[NewClientData] = None
    mark_name: Optional[str] = None
    mark_text: Optional[str] = None
    mark_type: Optional[MarkType] = None
    business_description: Optional[str] = Field(default=None, max_length=5000)
    goods_services: Optional[str] = Field(default=None, max_length=5000)
    description_of_mark: Optional[str] = Field(default=None, max_length=5000)


def _require_write_access(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для приёма обращений",
        )


def _require_intake_access(user: User, payload: IntakeRequest) -> None:
    """Клиент может создать только собственную новую заявку.

    Привязка к существующему клиенту или чужому делу остаётся операцией
    сотрудника: иначе идентификатор в запросе позволил бы затронуть чужие данные.
    """
    if user.role is not UserRole.client:
        _require_write_access(user)
        return
    if (
        not payload.create_case
        or payload.new_client is None
        or payload.client_id is not None
        or payload.target_case_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Клиент может создать только новую заявку со своими данными",
        )


async def _load_event(session: AsyncSession, event_id: int) -> InboundEvent:
    event = (
        await session.execute(
            select(InboundEvent)
            .where(InboundEvent.id == event_id)
            .options(selectinload(InboundEvent.attachments))
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Обращение {event_id} не найдено",
        )
    return event


@router.post(
    "/events",
    status_code=status.HTTP_201_CREATED,
    summary="Принять обращение и при необходимости создать дело",
)
async def create_intake(
    payload: IntakeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Зарегистрировать обращение от клиента.

    Повторная отправка того же обращения не создаёт дубликат: ключ
    идемпотентности вычисляется из содержимого, если не передан явно.
    """
    _require_intake_access(current_user, payload)

    result = await inbound.register_event(
        session,
        inbound.InboundPayload(
            source=SourceChannel.manual_upload,
            sender=payload.sender,
            subject=payload.subject,
            body_text=payload.body_text,
            external_event_id=payload.external_event_id,
            idempotency_key=payload.idempotency_key,
            links=payload.links,
            raw_payload=payload.model_dump(mode="json"),
        ),
        user_id=current_user.id,
    )

    if result.is_duplicate:
        event = await _load_event(session, result.event.id)
        return {
            **inbound.serialize_event(event),
            "is_duplicate": True,
            "notice": (
                "Обращение с таким содержимым уже принято. "
                "Повторная регистрация не выполнена."
            ),
        }

    event = result.event
    created_case_id: int | None = None

    try:
        if payload.target_case_id:
            await inbound.link_to_case(session, event, payload.target_case_id)
        elif payload.create_case:
            application = await inbound.create_case_from_event(
                session,
                event,
                client_id=payload.client_id,
                new_client=payload.new_client.model_dump() if payload.new_client else None,
                mark_name=payload.mark_name,
                mark_text=payload.mark_text or payload.mark_name,
                mark_type=payload.mark_type,
                business_description=payload.business_description,
                goods_services=payload.goods_services,
                description_of_mark=payload.description_of_mark,
                user_id=current_user.id,
            )
            created_case_id = application.id
            profile = current_user.applicant_profile_json or {}
            if current_user.role is UserRole.client and profile and payload.new_client:
                submitted = payload.new_client.model_dump()
                matched = {
                    key: value
                    for key, value in submitted.items()
                    if key in profile and value not in (None, "") and str(value).strip() == str(profile.get(key) or "").strip()
                }
                if matched:
                    session.add(
                        AuditLog(
                            user_id=current_user.id,
                            application_id=application.id,
                            action="application.prefilled_from_profile",
                            entity_type="TrademarkApplicationDraft",
                            entity_id=str(application.id),
                            new_value_json=matched,
                        )
                    )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=created_case_id or payload.target_case_id,
            action="inbound.received",
            entity_type="InboundEvent",
            entity_id=str(event.id),
            new_value_json={
                "source": event.source.value,
                "status": event.status.value,
                "case_id": event.target_case_id,
            },
        )
    )
    await session.flush()

    loaded = await _load_event(session, event.id)
    return {
        **inbound.serialize_event(loaded),
        "is_duplicate": False,
        "created_case_id": created_case_id,
    }


@router.post(
    "/events/{event_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="Приложить документ, присланный клиентом",
)
async def add_attachment(
    event_id: int,
    file: UploadFile = File(..., description="PDF, DOCX, TXT, PNG или JPG"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Загрузить вложение обращения.

    Файл проходит те же проверки и тот же разбор, что и документ,
    загруженный в дело напрямую. Отклонённый файл фиксируется в
    обращении с причиной — юрист должен видеть, что прислал клиент.
    """
    _require_write_access(current_user)
    event = await _load_event(session, event_id)

    content = await file.read()
    filename = file_storage.normalize_upload_filename(file.filename or "upload")

    try:
        stored = file_storage.save_upload(content, filename)
    except file_storage.FileValidationError as exc:
        await inbound.attach_document(
            session,
            event,
            document_id=None,
            original_filename=filename,
            error_message=str(exc),
        )
        await session.flush()
        # Не 400: обращение принято, отклонено конкретное вложение.
        return {
            "accepted": False,
            "original_filename": filename,
            "error_message": str(exc),
        }

    document = SourceDocument(
        application_id=event.target_case_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        stored_path=stored.stored_path,
        declared_content_type=file.content_type,
        detected_mime=stored.detected_mime,
        file_size=stored.size,
        sha256=stored.sha256,
        # Канал сохраняется: позже сюда встанут crm и email.
        source_channel=event.source,
        processing_status=DocumentProcessingStatus.extracting,
    )
    session.add(document)
    await session.flush()

    try:
        pages = extract_pages_from_bytes(content, filename)
    except (NoTextLayerError, UnsupportedDocumentType) as exc:
        reason = str(exc)
        pages = None
    except Exception as exc:  # noqa: BLE001
        reason = f"Не удалось разобрать файл (возможно, он повреждён): {exc}"
        pages = None

    if pages is None:
        document.processing_status = DocumentProcessingStatus.failed
        document.error_message = reason
    else:
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
        classification = classify_document("\n".join(p.text for p in pages))
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

    await inbound.attach_document(
        session,
        event,
        document_id=document.id,
        original_filename=filename,
    )
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=event.target_case_id,
            action="inbound.attachment",
            entity_type="InboundEvent",
            entity_id=str(event.id),
            new_value_json={"sha256": stored.sha256},
        )
    )
    await session.flush()

    return {
        "accepted": True,
        "document_id": document.id,
        "original_filename": filename,
        "document_kind": document.document_kind.value,
        "processing_status": document.processing_status.value,
        "page_count": document.page_count,
        "error_message": document.error_message,
    }


@router.get("/events", summary="Список обращений")
async def list_events(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    events = (
        (
            await session.execute(
                select(InboundEvent)
                .options(selectinload(InboundEvent.attachments))
                .order_by(InboundEvent.id.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [inbound.serialize_event(event) for event in events],
        "total": len(events),
    }


@router.get("/events/{event_id}", summary="Карточка обращения")
async def get_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = await _load_event(session, event_id)
    return inbound.serialize_event(event)
