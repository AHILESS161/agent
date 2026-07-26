"""Извлечение реквизитов, сверка полей и подтверждение специалистом.

Связующий слой между детерминированным извлечением
(``app.document_processing``) и интерфейсом специалиста.

Ключевое ограничение: ни одно значение не попадает в карточку дела
и в документы автоматически. Система показывает, что нашла, откуда
и с какой уверенностью, — решение принимает человек.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.document_processing.extractors import extract_registry_fields
from app.document_processing.mappers import build_reconciliation
from app.document_processing.extractors.registry import (
    ExtractedFieldResult,
    FieldCandidateResult,
)
from app.infrastructure.database.models import (
    AuditLog,
    ConfirmationAction,
    DocumentKind,
    DocumentPage,
    ExtractedField,
    ExtractionMethod,
    FieldCandidate,
    FieldConfirmation,
    FieldStatus,
    SourceDocument,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session

logger = get_logger(__name__)

router = APIRouter(tags=["extraction"])

_WRITE_ROLES = {UserRole.admin, UserRole.lawyer, UserRole.manager}

# Типы документов, для которых есть детерминированные паттерны.
_EXTRACTABLE = {
    DocumentKind.egrul_extract: "egrul",
    DocumentKind.egrip_extract: "egrip",
    DocumentKind.unknown_registry_extract: "egrul",
}


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------

class ConfirmFieldRequest(BaseModel):
    action: ConfirmationAction
    value: str | None = Field(
        default=None, description="Новое значение — обязательно для action=edit"
    )
    candidate_id: int | None = Field(
        default=None, description="Выбранный кандидат при конфликте"
    )
    reason: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

def _require_write_access(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения данных дела",
        )


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


def _mask(value: str | None) -> str | None:
    """Маскировать персональные данные для логов."""
    if not value:
        return value
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def _serialize_field(field: ExtractedField) -> dict[str, Any]:
    return {
        "id": field.id,
        "field_path": field.field_path,
        "label": field.label,
        "raw_value": field.raw_value,
        "normalized_value": field.normalized_value,
        "status": field.status.value,
        "confidence": field.confidence,
        "page_number": field.page_number,
        "pattern_id": field.pattern_id,
        "extraction_method": field.extraction_method.value,
        "validation_error": field.validation_error,
        "candidate_count": field.candidate_count,
        "is_sensitive": field.is_sensitive,
        "source_snippet": field.source_snippet,
        "candidates": [
            {
                "id": c.id,
                "raw_value": c.raw_value,
                "normalized_value": c.normalized_value,
                "pattern_id": c.pattern_id,
                "confidence": c.confidence,
                "page_number": c.page_number,
                "validation_passed": c.validation_passed,
                "is_selected": c.is_selected,
            }
            for c in field.candidates
        ],
    }


def _persist(
    document: SourceDocument, results: list[ExtractedFieldResult]
) -> list[ExtractedField]:
    """Превратить результаты извлечения в ORM-объекты."""
    rows: list[ExtractedField] = []
    for result in results:
        row = ExtractedField(
            document_id=document.id,
            application_id=document.application_id,
            field_path=result.field_id,
            label=result.label,
            raw_value=result.value,
            normalized_value=result.normalized_value,
            source_snippet=result.source_snippet,
            page_number=result.page_number,
            pattern_id=result.pattern_id,
            extraction_method=result.extraction_method,
            confidence=result.confidence,
            status=result.status,
            validation_error=result.validation_error,
            candidate_count=len(result.candidates),
            is_sensitive=result.is_sensitive,
        )
        row.candidates = [_candidate(c) for c in result.candidates]
        rows.append(row)
    return rows


def _candidate(candidate: FieldCandidateResult) -> FieldCandidate:
    return FieldCandidate(
        raw_value=candidate.raw_value,
        normalized_value=candidate.normalized_value,
        source_snippet=candidate.source_snippet,
        page_number=candidate.page_number,
        pattern_id=candidate.pattern_id,
        extraction_method=candidate.extraction_method,
        confidence=candidate.confidence,
        validation_passed=candidate.validation_passed,
    )


# ---------------------------------------------------------------------------
# Извлечение
# ---------------------------------------------------------------------------

@router.post(
    "/source-documents/{document_id}/extract",
    summary="Извлечь реквизиты из документа (regex, без LLM)",
)
async def extract_fields(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Запустить детерминированное извлечение реквизитов.

    Повторный запуск заменяет предыдущий результат: подтверждённые
    специалистом поля при этом сохраняются, чтобы его работа не терялась.
    """
    _require_write_access(current_user)
    document = await _load_document(session, document_id)

    pattern_set = _EXTRACTABLE.get(document.document_kind)
    if pattern_set is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Для типа документа '{document.document_kind.value}' "
                "правила извлечения не заданы. Подтвердите тип документа."
            ),
        )

    pages_result = await session.execute(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    pages = [(p.page_number, p.text_content or "") for p in pages_result.scalars().all()]
    if not pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="У документа нет извлечённого текста",
        )

    # Сохраняем поля, уже подтверждённые специалистом.
    existing_result = await session.execute(
        select(ExtractedField).where(ExtractedField.document_id == document_id)
    )
    preserved: set[str] = set()
    for existing in existing_result.scalars().all():
        if existing.status is FieldStatus.confirmed:
            preserved.add(existing.field_path)
        else:
            await session.delete(existing)
    await session.flush()

    results = extract_registry_fields(pages, pattern_set)
    fresh = [r for r in results if r.field_id not in preserved]
    for row in _persist(document, fresh):
        session.add(row)

    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=document.application_id,
            action="document.extract",
            entity_type="SourceDocument",
            entity_id=str(document.id),
            new_value_json={
                "fields_extracted": len(fresh),
                "preserved_confirmed": len(preserved),
                "method": "regex",
            },
        )
    )
    await session.flush()

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status.value] = counts.get(result.status.value, 0) + 1

    logger.info(
        "Извлечение выполнено",
        document_id=document_id,
        user_id=current_user.id,
        fields=len(fresh),
        preserved=len(preserved),
    )

    return {
        "document_id": document_id,
        "fields_extracted": len(fresh),
        "preserved_confirmed_fields": len(preserved),
        "by_status": counts,
        "extraction_method": "regex",
        "llm_used": False,
        "notice": (
            "Значения извлечены автоматически и требуют проверки специалистом. "
            "Ни одно из них не подтверждено."
        ),
    }


@router.get(
    "/source-documents/{document_id}/fields",
    summary="Извлечённые поля документа",
)
async def list_extracted_fields(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_document(session, document_id)
    result = await session.execute(
        select(ExtractedField)
        .where(ExtractedField.document_id == document_id)
        .options(selectinload(ExtractedField.candidates))
        .order_by(ExtractedField.id)
    )
    fields = list(result.scalars().all())
    return {
        "document_id": document_id,
        "items": [_serialize_field(f) for f in fields],
        "total": len(fields),
    }


# ---------------------------------------------------------------------------
# Сверка с полями заявления
# ---------------------------------------------------------------------------

@router.get(
    "/applications/{application_id}/field-reconciliation",
    summary="Сверка: выписка -> дело -> заявление",
)
async def field_reconciliation(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Таблица сопоставления для специалиста.

    Показывает по каждому полю: значение из документа, значение в деле,
    целевое поле заявления, статус и доступные действия.
    """
    application = (
        await session.execute(
            select(TrademarkApplicationDraft)
            # Клиент нужен для сверки с карточкой дела; в async-сессии
            # ленивая подгрузка связи невозможна.
            .options(selectinload(TrademarkApplicationDraft.client))
            .where(TrademarkApplicationDraft.id == application_id)
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Дело {application_id} не найдено",
        )

    fields_result = await session.execute(
        select(ExtractedField)
        .where(ExtractedField.application_id == application_id)
        .options(selectinload(ExtractedField.candidates))
    )
    stored = list(fields_result.scalars().all())

    # ORM-записи -> объекты предметной области для движка маппинга.
    domain = [
        ExtractedFieldResult(
            field_id=f.field_path,
            label=f.label or f.field_path,
            status=f.status,
            is_sensitive=f.is_sensitive,
            value=f.raw_value,
            normalized_value=f.normalized_value,
            confidence=f.confidence,
            page_number=f.page_number,
            pattern_id=f.pattern_id,
            source_snippet=f.source_snippet or "",
            validation_error=f.validation_error,
            extraction_method=f.extraction_method,
            candidates=[
                FieldCandidateResult(
                    raw_value=c.raw_value,
                    normalized_value=c.normalized_value or "",
                    pattern_id=c.pattern_id or "",
                    confidence=c.confidence or 0.0,
                    page_number=c.page_number,
                    validation_passed=c.validation_passed,
                )
                for c in f.candidates
            ],
        )
        for f in stored
    ]

    # Текущие значения карточки дела для выявления расхождений.
    case_values = {
        "case.applicant.full_name": application.client.full_name_or_company_name
        if application.client
        else None,
        "case.applicant.inn": application.client.inn if application.client else None,
        "case.applicant.ogrn": application.client.ogrn_or_ogrnip
        if application.client
        else None,
    }
    case_values = {k: v for k, v in case_values.items() if v}

    client_type = (
        application.client.type.value if application.client else None
    )
    rows, summary = build_reconciliation(
        domain, case_values, client_type=client_type
    )
    field_ids = {f.field_path: f.id for f in stored}

    return {
        "application_id": application_id,
        "summary": summary,
        "items": [
            {
                "extracted_field_id": field_ids.get(row.registry_field or ""),
                "label": row.label,
                "registry_field": row.registry_field,
                "case_field": row.case_field,
                "application_field": row.application_field,
                "status": row.status.value,
                "registry_value": row.registry_value,
                "registry_raw_value": row.registry_raw_value,
                "case_value": row.case_value,
                "default_value": row.default_value,
                "confidence": row.confidence,
                "page_number": row.page_number,
                "pattern_id": row.pattern_id,
                "extraction_method": row.extraction_method,
                "source_snippet": row.source_snippet,
                "required_for_application": row.required_for_application,
                "critical": row.critical,
                "is_sensitive": row.is_sensitive,
                "normalization_changed": row.normalization_changed,
                "validation_error": row.validation_error,
                "note": row.note,
                "candidates": row.candidates,
                "available_actions": row.available_actions,
                "blocks_document_generation": row.blocks_document_generation,
            }
            for row in rows
        ],
        "disclaimer": (
            "Результаты сформированы с применением автоматической обработки "
            "и носят предварительный информационный характер. "
            "Они требуют проверки специалистом."
        ),
    }


# ---------------------------------------------------------------------------
# Подтверждение специалистом
# ---------------------------------------------------------------------------

@router.post(
    "/extracted-fields/{field_id}/confirm",
    summary="Решение специалиста по полю",
)
async def confirm_field(
    field_id: int,
    payload: ConfirmFieldRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Принять, изменить, отклонить или оставить поле пустым.

    Каждое решение записывается в историю с указанием пользователя,
    прежнего и нового значения.
    """
    _require_write_access(current_user)

    result = await session.execute(
        select(ExtractedField)
        .where(ExtractedField.id == field_id)
        .options(selectinload(ExtractedField.candidates))
    )
    field = result.scalar_one_or_none()
    if field is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Поле {field_id} не найдено",
        )

    previous_value = field.normalized_value
    new_value = previous_value
    selected_candidate_id = payload.candidate_id

    if payload.action is ConfirmationAction.accept:
        if payload.candidate_id is not None:
            candidate = next(
                (c for c in field.candidates if c.id == payload.candidate_id), None
            )
            if candidate is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Указанный кандидат не относится к этому полю",
                )
            for other in field.candidates:
                other.is_selected = other.id == candidate.id
            new_value = candidate.normalized_value or candidate.raw_value
        elif field.status is FieldStatus.conflict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Поле содержит несколько несовпадающих значений — "
                    "укажите candidate_id или введите значение вручную"
                ),
            )
        elif not new_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нечего принимать: значение не найдено",
            )
        field.status = FieldStatus.confirmed

    elif payload.action is ConfirmationAction.edit:
        if not payload.value or not payload.value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для действия 'edit' требуется значение",
            )
        new_value = payload.value.strip()
        field.normalized_value = new_value
        field.raw_value = new_value
        # Значение введено человеком — источником становится он.
        field.extraction_method = ExtractionMethod.manual
        field.confidence = None
        field.pattern_id = None
        field.validation_error = None
        field.status = FieldStatus.confirmed

    elif payload.action is ConfirmationAction.reject:
        new_value = None
        field.status = FieldStatus.rejected

    elif payload.action is ConfirmationAction.leave_empty:
        new_value = None
        field.status = FieldStatus.left_empty

    if payload.action is ConfirmationAction.accept and payload.candidate_id is not None:
        field.normalized_value = new_value

    session.add(
        FieldConfirmation(
            field_id=field.id,
            user_id=current_user.id,
            action=payload.action,
            previous_value=previous_value,
            new_value=new_value,
            selected_candidate_id=selected_candidate_id,
            reason=payload.reason,
        )
    )
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=field.application_id,
            action=f"field.{payload.action.value}",
            entity_type="ExtractedField",
            entity_id=str(field.id),
            # Персональные данные в аудите маскируются.
            old_value_json={
                "value": _mask(previous_value) if field.is_sensitive else previous_value
            },
            new_value_json={
                "value": _mask(new_value) if field.is_sensitive else new_value,
                "field_path": field.field_path,
            },
        )
    )
    await session.flush()

    logger.info(
        "Решение специалиста по полю",
        field_id=field.id,
        user_id=current_user.id,
        action=payload.action.value,
        field_path=field.field_path,
    )

    return _serialize_field(field)


@router.get(
    "/extracted-fields/{field_id}/history",
    summary="История решений по полю",
)
async def field_history(
    field_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    result = await session.execute(
        select(FieldConfirmation)
        .where(FieldConfirmation.field_id == field_id)
        .order_by(FieldConfirmation.created_at.desc())
    )
    history = list(result.scalars().all())
    return {
        "field_id": field_id,
        "items": [
            {
                "id": h.id,
                "user_id": h.user_id,
                "action": h.action.value,
                "previous_value": h.previous_value,
                "new_value": h.new_value,
                "reason": h.reason,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ],
        "total": len(history),
    }
