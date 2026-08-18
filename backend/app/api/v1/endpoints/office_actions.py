"""Работа с уведомлениями Роспатента и проектами ответов на них."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_llm_provider
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.infrastructure.database.models import (
    AuditLog,
    DocumentPage,
    OfficeActionResponse,
    SourceDocument,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.services.office_action_response import generate_response, render_response_docx

logger = get_logger(__name__)
router = APIRouter(tags=["office actions"])

HOMOGENEITY_CRITERIA = {
    "purpose", "nature", "material", "consumers", "distribution_channels",
    "interchangeability", "joint_use", "common_origin",
}
DISTINCTIVENESS_CRITERIA = {
    "first_use_date", "sales_territory", "revenue_and_sales", "advertising_expenses",
    "media_publications", "contracts_and_catalogs", "website_marketplace_stats",
    "surveys", "product_packaging_photos",
}


class ConfirmedFact(BaseModel):
    criterion: str
    label: str = Field(min_length=1, max_length=255)
    confirmed: bool = False
    fact: str = Field(default="", max_length=5000)
    document_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def confirmed_fact_has_text(self) -> "ConfirmedFact":
        if self.confirmed and not self.fact.strip():
            raise ValueError("Для отмеченного пункта опишите конкретный факт")
        return self


class OfficeActionCreate(BaseModel):
    notice_document_id: int
    response_deadline: str | None = Field(default=None, max_length=32)
    homogeneity_facts: list[ConfirmedFact] = Field(default_factory=list)
    distinctiveness_evidence: list[ConfirmedFact] = Field(default_factory=list)
    additional_facts: str | None = Field(default=None, max_length=10000)


class OfficeActionUpdate(OfficeActionCreate):
    pass


async def _application(session: AsyncSession, application_id: int) -> TrademarkApplicationDraft:
    item = await session.scalar(
        select(TrademarkApplicationDraft).where(TrademarkApplicationDraft.id == application_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return item


def _require_access(user: User, application: TrademarkApplicationDraft) -> None:
    if user.role is not UserRole.admin and user.id not in {
        application.created_by_user_id,
        application.assigned_lawyer_id,
        application.assigned_manager_id,
    }:
        raise HTTPException(status_code=403, detail="Нет доступа к заявке")


async def _office_action(
    session: AsyncSession, application_id: int, response_id: int
) -> OfficeActionResponse:
    item = await session.scalar(
        select(OfficeActionResponse).where(
            OfficeActionResponse.id == response_id,
            OfficeActionResponse.application_id == application_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Проект ответа не найден")
    return item


def _fact_dicts(items: list[ConfirmedFact], allowed: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if item.criterion not in allowed:
            raise HTTPException(status_code=422, detail=f"Неизвестный критерий: {item.criterion}")
        if item.criterion in seen:
            raise HTTPException(status_code=422, detail=f"Критерий повторяется: {item.criterion}")
        seen.add(item.criterion)
        result.append(item.model_dump())
    return result


async def _documents(
    session: AsyncSession, application_id: int, ids: set[int]
) -> dict[int, SourceDocument]:
    if not ids:
        return {}
    result = await session.execute(
        select(SourceDocument).where(
            SourceDocument.application_id == application_id, SourceDocument.id.in_(ids)
        )
    )
    documents = {item.id: item for item in result.scalars().all()}
    if set(documents) != ids:
        raise HTTPException(status_code=422, detail="Один из файлов не относится к этой заявке")
    return documents


async def _validated_payload(
    session: AsyncSession, application_id: int, payload: OfficeActionCreate
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    homogeneity = _fact_dicts(payload.homogeneity_facts, HOMOGENEITY_CRITERIA)
    distinctiveness = _fact_dicts(payload.distinctiveness_evidence, DISTINCTIVENESS_CRITERIA)
    ids = {payload.notice_document_id}
    for item in [*homogeneity, *distinctiveness]:
        ids.update(item["document_ids"])
    await _documents(session, application_id, ids)
    return homogeneity, distinctiveness


async def _document_names(
    session: AsyncSession, application_id: int, item: OfficeActionResponse
) -> dict[int, str]:
    ids: set[int] = set()
    for fact in [*(item.homogeneity_facts_json or []), *(item.distinctiveness_evidence_json or [])]:
        ids.update(fact.get("document_ids", []))
    return {key: value.original_filename for key, value in (await _documents(session, application_id, ids)).items()}


def _serialize(item: OfficeActionResponse, notice_name: str | None = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "application_id": item.application_id,
        "notice_document_id": item.notice_document_id,
        "notice_filename": notice_name,
        "status": item.status,
        "response_deadline": item.response_deadline,
        "homogeneity_facts": item.homogeneity_facts_json or [],
        "distinctiveness_evidence": item.distinctiveness_evidence_json or [],
        "additional_facts": item.additional_facts or "",
        "notice_summary": item.notice_summary,
        "response_summary": item.response_summary,
        "missing_evidence": item.missing_evidence_json or [],
        "draft_text": item.draft_text,
        "llm_model": item.llm_model,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/applications/{application_id}/office-actions")
async def list_office_actions(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _application(session, application_id)
    _require_access(current_user, application)
    result = await session.execute(
        select(OfficeActionResponse, SourceDocument.original_filename)
        .join(SourceDocument, SourceDocument.id == OfficeActionResponse.notice_document_id)
        .where(OfficeActionResponse.application_id == application_id)
        .order_by(OfficeActionResponse.created_at.desc())
    )
    items = [_serialize(item, filename) for item, filename in result.all()]
    return {"items": items, "total": len(items)}


@router.post("/applications/{application_id}/office-actions", status_code=status.HTTP_201_CREATED)
async def create_office_action(
    application_id: int,
    payload: OfficeActionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _application(session, application_id)
    _require_access(current_user, application)
    homogeneity, distinctiveness = await _validated_payload(session, application_id, payload)
    notice = await session.get(SourceDocument, payload.notice_document_id)
    item = OfficeActionResponse(
        application_id=application_id,
        notice_document_id=payload.notice_document_id,
        created_by_user_id=current_user.id,
        response_deadline=payload.response_deadline,
        homogeneity_facts_json=homogeneity,
        distinctiveness_evidence_json=distinctiveness,
        additional_facts=payload.additional_facts,
    )
    session.add(item)
    await session.flush()
    return _serialize(item, notice.original_filename if notice else None)


@router.put("/applications/{application_id}/office-actions/{response_id}")
async def update_office_action(
    application_id: int,
    response_id: int,
    payload: OfficeActionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _application(session, application_id)
    _require_access(current_user, application)
    item = await _office_action(session, application_id, response_id)
    homogeneity, distinctiveness = await _validated_payload(session, application_id, payload)
    item.notice_document_id = payload.notice_document_id
    item.response_deadline = payload.response_deadline
    item.homogeneity_facts_json = homogeneity
    item.distinctiveness_evidence_json = distinctiveness
    item.additional_facts = payload.additional_facts
    item.status = "draft"
    item.draft_text = None
    item.notice_summary = None
    item.response_summary = None
    item.missing_evidence_json = []
    session.add(item)
    await session.flush()
    notice = await session.get(SourceDocument, item.notice_document_id)
    return _serialize(item, notice.original_filename if notice else None)


@router.post("/applications/{application_id}/office-actions/{response_id}/generate")
async def generate_office_action(
    application_id: int,
    response_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    application = await _application(session, application_id)
    _require_access(current_user, application)
    item = await _office_action(session, application_id, response_id)
    pages = await session.scalars(
        select(DocumentPage).where(DocumentPage.document_id == item.notice_document_id).order_by(DocumentPage.page_number)
    )
    notice_text = "\n".join(page.text_content or "" for page in pages.all())
    names = await _document_names(session, application_id, item)
    try:
        generated = await generate_response(
            llm=get_llm_provider(),
            application_context={
                "application_id": application.id,
                "mark_name": application.mark_name,
                "mark_type": application.mark_type.value if application.mark_type else None,
                "goods_and_services": application.goods_services_raw,
            },
            notice_text=notice_text,
            homogeneity_facts=item.homogeneity_facts_json or [],
            distinctiveness_evidence=item.distinctiveness_evidence_json or [],
            additional_facts=item.additional_facts,
            attachment_names=names,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось подготовить ответ Роспатенту", application_id=application_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Не удалось подготовить черновик. Сохранённые факты не потеряны — повторите позже.") from exc
    item.notice_summary = generated["notice_summary"]
    item.response_summary = generated["response_summary"]
    item.missing_evidence_json = generated["missing_evidence"]
    item.draft_text = generated["draft_text"]
    item.llm_model = generated["llm_model"]
    item.status = "generated"
    session.add(AuditLog(user_id=current_user.id, application_id=application_id, action="office_action.generated", entity_type="OfficeActionResponse", entity_id=str(item.id)))
    await session.flush()
    # SQLite/PostgreSQL могут вычислять ``updated_at`` на стороне БД. Явное
    # обновление не допускает ленивый SQL-запрос при синхронной сериализации.
    await session.refresh(item)
    notice = await session.get(SourceDocument, item.notice_document_id)
    return _serialize(item, notice.original_filename if notice else None)


@router.get("/applications/{application_id}/office-actions/{response_id}/download")
async def download_office_action(
    application_id: int,
    response_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    application = await _application(session, application_id)
    _require_access(current_user, application)
    item = await _office_action(session, application_id, response_id)
    if not item.draft_text:
        raise HTTPException(status_code=409, detail="Сначала сформируйте черновик ответа")
    names = list((await _document_names(session, application_id, item)).values())
    payload = render_response_docx(application_id=application_id, mark_name=application.mark_name or "без названия", draft_text=item.draft_text, attachment_names=names)
    filename = f"otvet-rospatent-{application_id}-{response_id}.docx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
