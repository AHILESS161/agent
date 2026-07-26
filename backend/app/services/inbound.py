"""Приём входящих обращений.

Пока интеграции с CRM и почтой нет, обращение вносит юрист вручную.
Но путь обработки уже единый: и ручной ввод, и будущий webhook создают
один и тот же ``InboundEvent`` и проходят одинаковые шаги — сохранение
исходных данных, привязка вложений, создание дела-черновика.

Повторная доставка одного события не создаёт дубликат: ключ
идемпотентности вычисляется из содержимого, если не передан явно.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Client,
    ClientType,
    InboundAttachment,
    InboundEvent,
    InboundStatus,
    SourceChannel,
    TrademarkApplicationDraft,
)

logger = get_logger(__name__)


@dataclass
class InboundPayload:
    """Нормализованное входящее событие.

    Единый формат для всех каналов: то, что сейчас заполняет юрист,
    позже будет приходить из CRM или письма.
    """

    source: SourceChannel
    sender: str | None = None
    subject: str | None = None
    body_text: str | None = None
    external_event_id: str | None = None
    idempotency_key: str | None = None
    links: list[str] | None = None
    metadata: dict[str, Any] | None = None
    raw_payload: dict[str, Any] | None = None

    def compute_idempotency_key(self) -> str:
        """Ключ из содержимого события.

        Позволяет распознать повтор, даже если источник не передал
        собственный идентификатор.
        """
        if self.idempotency_key:
            return self.idempotency_key
        if self.external_event_id:
            return f"{self.source.value}:{self.external_event_id}"

        # В ключ входит всё содержимое события, а не только сопроводительное
        # письмо. Иначе два разных дела с пустыми полями «от кого» и «текст
        # обращения» дают одинаковый ключ, и второе дело считается повтором
        # первого — пользователя возвращает на чужую заявку.
        material = json.dumps(
            {
                "source": self.source.value,
                "sender": self.sender,
                "subject": self.subject,
                "body": (self.body_text or "")[:2000],
                "payload": self.raw_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
        return f"{self.source.value}:{digest}"


@dataclass
class InboundResult:
    event: InboundEvent
    is_duplicate: bool
    created_case_id: int | None = None


async def find_by_idempotency_key(
    session: AsyncSession, key: str
) -> InboundEvent | None:
    return (
        await session.execute(
            select(InboundEvent).where(InboundEvent.idempotency_key == key)
        )
    ).scalar_one_or_none()


async def register_event(
    session: AsyncSession,
    payload: InboundPayload,
    user_id: int | None = None,
) -> InboundResult:
    """Зарегистрировать обращение.

    Если событие с таким ключом уже принято, возвращается существующее:
    повтор не создаёт ни второго события, ни второго дела.
    """
    key = payload.compute_idempotency_key()

    existing = await find_by_idempotency_key(session, key)
    if existing is not None:
        logger.info(
            "Повторное обращение проигнорировано",
            idempotency_key=key,
            event_id=existing.id,
        )
        return InboundResult(
            event=existing,
            is_duplicate=True,
            created_case_id=existing.target_case_id,
        )

    event = InboundEvent(
        source=payload.source,
        external_event_id=payload.external_event_id,
        idempotency_key=key,
        sender=payload.sender,
        subject=payload.subject,
        body_text=payload.body_text,
        links_json=payload.links or [],
        metadata_json=payload.metadata or {},
        raw_payload_json=payload.raw_payload,
        status=InboundStatus.received,
        created_by_user_id=user_id,
    )
    session.add(event)
    await session.flush()

    logger.info(
        "Обращение принято",
        event_id=event.id,
        source=payload.source.value,
        idempotency_key=key,
    )
    return InboundResult(event=event, is_duplicate=False)


async def link_to_case(
    session: AsyncSession, event: InboundEvent, application_id: int
) -> InboundEvent:
    """Привязать обращение к существующему делу."""
    event.target_case_id = application_id
    event.status = InboundStatus.linked
    await session.flush()
    return event


async def create_case_from_event(
    session: AsyncSession,
    event: InboundEvent,
    *,
    client_id: int | None,
    new_client: dict[str, Any] | None,
    mark_name: str | None,
    mark_text: str | None,
    business_description: str | None,
    goods_services: str | None,
    user_id: int | None = None,
) -> TrademarkApplicationDraft:
    """Создать дело-черновик из обращения.

    Клиент либо выбирается из существующих, либо создаётся здесь же:
    юрист заносит реквизиты, присланные клиентом, до того как система
    сверит их с выпиской.
    """
    if client_id is None:
        if not new_client or not new_client.get("full_name_or_company_name"):
            raise ValueError(
                "Не указан клиент: выберите существующего или заполните наименование"
            )
        client = Client(
            type=ClientType(new_client.get("type") or ClientType.company.value),
            full_name_or_company_name=new_client["full_name_or_company_name"],
            short_name=new_client.get("short_name"),
            contact_person=new_client.get("contact_person"),
            email=new_client.get("email"),
            phone=new_client.get("phone"),
            address=new_client.get("address"),
            inn=new_client.get("inn"),
            ogrn_or_ogrnip=new_client.get("ogrn_or_ogrnip"),
            created_by_user_id=user_id,
        )
        session.add(client)
        await session.flush()
        client_id = client.id

    application = TrademarkApplicationDraft(
        client_id=client_id,
        mark_name=mark_name,
        mark_text=mark_text,
        business_description=business_description,
        goods_services_raw=goods_services,
        # Текст обращения сохраняется в примечаниях: он часто содержит
        # пояснения клиента, которых нет в структурированных полях.
        notes=event.body_text,
    )
    session.add(application)
    await session.flush()

    event.target_case_id = application.id
    event.status = InboundStatus.case_created
    await session.flush()

    logger.info(
        "Дело создано из обращения",
        event_id=event.id,
        application_id=application.id,
    )
    return application


async def attach_document(
    session: AsyncSession,
    event: InboundEvent,
    *,
    document_id: int | None,
    original_filename: str,
    error_message: str | None = None,
) -> InboundAttachment:
    """Связать загруженный документ с обращением.

    Отклонённые файлы тоже фиксируются: юрист должен видеть, что именно
    прислал клиент и почему файл не принят.
    """
    attachment = InboundAttachment(
        event_id=event.id,
        document_id=document_id,
        original_filename=original_filename,
        error_message=error_message,
    )
    session.add(attachment)
    await session.flush()
    return attachment


def serialize_event(event: InboundEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "source": event.source.value,
        "external_event_id": event.external_event_id,
        "idempotency_key": event.idempotency_key,
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "sender": event.sender,
        "subject": event.subject,
        "body_text": event.body_text,
        "links": event.links_json or [],
        "metadata": event.metadata_json or {},
        "status": event.status.value,
        "target_case_id": event.target_case_id,
        "processing_note": event.processing_note,
        "created_by_user_id": event.created_by_user_id,
        "attachments": [
            {
                "id": attachment.id,
                "document_id": attachment.document_id,
                "original_filename": attachment.original_filename,
                "error_message": attachment.error_message,
                "accepted": attachment.document_id is not None,
            }
            for attachment in event.attachments
        ],
    }
