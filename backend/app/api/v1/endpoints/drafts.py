"""Черновики заявления: формирование, утверждение, экспорт."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.infrastructure.database.models import (
    ApplicationDraft,
    AuditLog,
    DraftStatus,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services import file_storage
from app.services.application_draft import create_draft, serialize_draft

logger = get_logger(__name__)

router = APIRouter(tags=["application-drafts"])

_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}
# Утверждать черновик может только специалист или администратор:
# это решение о содержании юридически значимого документа.
_APPROVE_ROLES = {UserRole.admin, UserRole.lawyer}


def _require(user: User, roles: set[UserRole], action: str) -> None:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Недостаточно прав: {action}",
        )


async def _load_application(
    session: AsyncSession, application_id: int
) -> TrademarkApplicationDraft:
    application = (
        await session.execute(
            select(TrademarkApplicationDraft).where(
                TrademarkApplicationDraft.id == application_id
            )
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Дело {application_id} не найдено",
        )
    return application


async def _load_draft(session: AsyncSession, draft_id: int) -> ApplicationDraft:
    draft = (
        await session.execute(
            select(ApplicationDraft).where(ApplicationDraft.id == draft_id)
        )
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Черновик {draft_id} не найден",
        )
    return draft


@router.post(
    "/applications/{application_id}/draft",
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать черновик заявления",
)
async def generate_draft(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Заполнить бланк заявления подтверждёнными данными дела.

    Поля со статусом «конфликт», «требует проверки» или «не найдено»
    остаются пустыми, а причина попадает в чек-лист.
    """
    _require(current_user, _WRITE_ROLES, "формирование черновика")
    application = await _load_application(session, application_id)

    draft = await create_draft(session, application, user_id=current_user.id)

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=application.id,
            action="draft.generated",
            entity_type="ApplicationDraft",
            entity_id=str(draft.id),
            new_value_json={
                "version": draft.version,
                "filled": len(draft.filled_fields_json or []),
                "skipped": len(draft.skipped_fields_json or []),
            },
        )
    )
    await session.flush()
    return serialize_draft(draft)


@router.get(
    "/applications/{application_id}/drafts",
    summary="Версии черновика заявления",
)
async def list_drafts(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_application(session, application_id)
    drafts = (
        (
            await session.execute(
                select(ApplicationDraft)
                .where(ApplicationDraft.application_id == application_id)
                .order_by(ApplicationDraft.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "application_id": application_id,
        "items": [serialize_draft(draft) for draft in drafts],
        "total": len(drafts),
    }


@router.post("/drafts/{draft_id}/approve", summary="Утвердить черновик")
async def approve_draft(
    draft_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Утвердить черновик. Только после этого возможен экспорт."""
    _require(current_user, _APPROVE_ROLES, "утверждение черновика")
    draft = await _load_draft(session, draft_id)

    draft.status = DraftStatus.approved_by_specialist
    draft.approved_by_user_id = current_user.id
    draft.approved_at = datetime.now(timezone.utc)

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=draft.application_id,
            action="draft.approved",
            entity_type="ApplicationDraft",
            entity_id=str(draft.id),
            new_value_json={"version": draft.version},
        )
    )
    await session.flush()

    logger.info(
        "Черновик утверждён",
        draft_id=draft.id,
        version=draft.version,
        user_id=current_user.id,
    )
    return serialize_draft(draft)


@router.get("/drafts/{draft_id}/download", summary="Скачать черновик")
async def download_draft(
    draft_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Выгрузить файл черновика.

    Экспорт разрешён только после утверждения специалистом: иначе
    неутверждённый документ уйдёт наружу как готовый.
    """
    draft = await _load_draft(session, draft_id)

    if draft.status not in (
        DraftStatus.approved_by_specialist,
        DraftStatus.exported,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Черновик не утверждён специалистом. "
                "Экспорт возможен только после утверждения."
            ),
        )

    if not draft.file_path:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Файл черновика отсутствует"
        )

    try:
        content = file_storage.read_file(draft.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл черновика отсутствует в хранилище",
        ) from exc

    if draft.status is not DraftStatus.exported:
        draft.status = DraftStatus.exported
        draft.exported_at = datetime.now(timezone.utc)
        session.add(
            AuditLog(
                user_id=current_user.id,
                application_id=draft.application_id,
                action="draft.exported",
                entity_type="ApplicationDraft",
                entity_id=str(draft.id),
                new_value_json={"version": draft.version},
            )
        )
        await session.flush()

    filename = f"zayavka-delo-{draft.application_id}-v{draft.version}.docx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
