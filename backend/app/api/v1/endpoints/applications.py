"""Trademark application draft endpoints — full CRUD + workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user, require_roles
from app.infrastructure.database.models import (
    AgentRun,
    AgentRunStatus,
    ApplicationStatus,
    AuditLog,
    Client,
    ClientRepresentative,
    ConflictDecision,
    ConflictSearchJob,
    ConflictSearchResult,
    DocumentPackage,
    DocumentTemplate,
    GenerationStatus,
    LegalFinding,
    LegalReview,
    NiceClassSuggestion,
    RecommendationMemo,
    SearchJobStatus,
    SourceDocument,
    Submission,
    SubmissionStatusEvent,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import get_session
from app.schemas.applications import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationResponse,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    ApplicationValidationResult,
    MarkDetailsSuggestionRecord,
    ValidationIssue,
)
from app.schemas.classification import (
    ClassApprovalRequest,
    ManualClassRequest,
    ClassSuggestionResponse,
    NiceClassSuggestionResponse,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.conflicts import (
    ConflictReviewDecisionRequest,
    ConflictSearchRequest,
    ConflictSearchResponse,
)
from app.schemas.documents import (
    DocumentApprovalRequest,
    DocumentGenerateRequest,
    DocumentPackageListResponse,
    DocumentPackageResponse,
)
from app.schemas.legal import (
    LegalReviewRequest,
    LegalReviewResponse,
)
from app.services.completeness_engine import ApplicationStage, CompletenessEngine
from app.services.data_confirmation import data_confirmation_state
from app.services.document_lifecycle import release_unreferenced_blobs
from app.services.state_machine import ApplicationStateMachine
from app.services.application_draft import load_mark_image_content
from app.services.mark_description import (
    DESCRIPTION_SCHEMA,
    build_mark_description_prompt,
    normalize_mark_language,
    normalize_mark_description,
    prepare_vision_image,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.agents.legal.query_variants import QueryVariantGenerator

router = APIRouter(prefix="/applications", tags=["applications"])
logger = get_logger(__name__)

_completeness_engine = CompletenessEngine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_app_or_404(
    application_id: int,
    session: AsyncSession,
    *,
    load_client: bool = False,
) -> TrademarkApplicationDraft:
    stmt = select(TrademarkApplicationDraft).where(
        TrademarkApplicationDraft.id == application_id
    )
    if load_client:
        stmt = stmt.options(
            selectinload(TrademarkApplicationDraft.client),
            selectinload(TrademarkApplicationDraft.representative),
        )
    result = await session.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    return app


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def _create_audit(
    session: AsyncSession,
    *,
    user: User,
    action: str,
    application: TrademarkApplicationDraft,
    old_val: dict | None = None,
    new_val: dict | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user.id,
        application_id=application.id,
        action=action,
        entity_type="TrademarkApplicationDraft",
        entity_id=str(application.id),
        old_value_json=old_val,
        new_value_json=new_val,
        ip_address=ip_address,
    )
    session.add(entry)


# Провайдеры живут в app.api.dependencies — единственный источник правды.
# Имена реэкспортируются, чтобы не ломать существующие импорты и тесты.
from app.api.dependencies import (  # noqa: E402
    _get_llm_provider,
    _get_prompt_registry,
    _get_registry_provider,
)


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------


def _is_owner(app: TrademarkApplicationDraft, user: User) -> bool:
    """Ведёт ли пользователь это дело."""
    return user.id in {
        app.created_by_user_id,
        app.assigned_lawyer_id,
        app.assigned_manager_id,
    }


def _ensure_access(app: TrademarkApplicationDraft, user: User) -> None:
    """Не позволять пользователю читать или менять чужое дело по прямому URL."""
    if user.role is not UserRole.admin and not _is_owner(app, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой заявке",
        )


def _visible_to(query, user: User):
    """Ограничить выборку делами, доступными пользователю.

    Поверенный ведёт свои дела: заведённые им самим и назначенные
    на него. Администратор видит всё — иначе он не разберётся
    в чужой работе.
    """
    if user.role is UserRole.admin:
        return query
    return query.where(
        or_(
            TrademarkApplicationDraft.created_by_user_id == user.id,
            TrademarkApplicationDraft.assigned_lawyer_id == user.id,
            TrademarkApplicationDraft.assigned_manager_id == user.id,
        )
    )


@router.get("", response_model=PaginatedResponse[ApplicationListItem])
async def list_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status_filter: Optional[ApplicationStatus] = Query(default=None, alias="status"),
    client_id: Optional[int] = Query(default=None),
    assigned_lawyer_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ApplicationListItem]:
    """Список дел с фильтрами.

    Поверенный видит свои дела: те, что завёл сам, и те, что на него
    назначены. Администратору видно всё — иначе он не сможет
    разобраться в чужой работе.
    """
    base_q = select(TrademarkApplicationDraft)
    base_q = _visible_to(base_q, current_user)
    if status_filter:
        base_q = base_q.where(TrademarkApplicationDraft.status == status_filter)
    if client_id is not None:
        base_q = base_q.where(TrademarkApplicationDraft.client_id == client_id)
    if assigned_lawyer_id is not None:
        base_q = base_q.where(
            TrademarkApplicationDraft.assigned_lawyer_id == assigned_lawyer_id
        )

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        base_q.offset(offset)
        .limit(page_size)
        .order_by(TrademarkApplicationDraft.id.desc())
    )
    apps = result.scalars().all()
    items = [ApplicationListItem.model_validate(a) for a in apps]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApplicationResponse:
    """Create a new application draft."""
    if payload.representative_id is not None:
        representative = (
            await session.execute(
                select(ClientRepresentative).where(
                    ClientRepresentative.id == payload.representative_id,
                    ClientRepresentative.client_id == payload.client_id,
                )
            )
        ).scalar_one_or_none()
        if representative is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Representative must belong to the application applicant",
            )
    app = TrademarkApplicationDraft(
        **payload.model_dump(), created_by_user_id=current_user.id
    )
    session.add(app)
    await session.flush()
    await session.refresh(app)

    await _create_audit(
        session,
        user=current_user,
        action="application_create",
        application=app,
        new_val={"client_id": app.client_id, "status": app.status.value},
        ip_address=_get_client_ip(request),
    )
    return ApplicationResponse.model_validate(app)


# ---------------------------------------------------------------------------
# Get / Update
# ---------------------------------------------------------------------------


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить дело",
)
async def delete_application(
    application_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Удалить дело со всеми материалами.

    Поданную заявку удалить нельзя: у неё есть внешние последствия,
    и след о ней должен остаться. Такое дело закрывают.
    """
    app = await _get_app_or_404(application_id, session)

    # Клиент и специалист распоряжаются только своими делами; чужое дело
    # удалить может только администратор.
    if current_user.role is not UserRole.admin and not _is_owner(app, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Дело ведёт другой специалист. Удалить чужое дело может "
                "только администратор."
            ),
        )

    if app.status in (ApplicationStatus.submitted, ApplicationStatus.closed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Поданное или закрытое дело удалить нельзя: сведения о нём "
                "должны сохраниться. Измените статус, если дело заведено "
                "по ошибке."
            ),
        )

    document_paths = list(
        (
            await session.execute(
                select(SourceDocument.stored_path).where(
                    SourceDocument.application_id == app.id
                )
            )
        ).scalars()
    )

    await _create_audit(
        session,
        user=current_user,
        action="application_delete",
        application=app,
        old_val={"status": app.status.value},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.delete(app)
    # Flush database cascades before releasing content-addressed blobs. The
    # same physical file may still be referenced by another case.
    await session.flush()
    await release_unreferenced_blobs(session, document_paths)


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApplicationResponse:
    """Get full application details."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    return ApplicationResponse.model_validate(app)


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApplicationResponse:
    """Update an application draft (only editable in draft/info_requested/info_received states)."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)

    old_val = {"status": app.status.value}
    update_values = payload.model_dump(exclude_none=True)
    if "representative_id" in payload.model_fields_set:
        update_values["representative_id"] = payload.representative_id
    representative_id = update_values.get("representative_id")
    if representative_id is not None:
        representative = (
            await session.execute(
                select(ClientRepresentative).where(
                    ClientRepresentative.id == representative_id,
                    ClientRepresentative.client_id == app.client_id,
                )
            )
        ).scalar_one_or_none()
        if representative is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Representative must belong to the application applicant",
            )
    for field, value in update_values.items():
        setattr(app, field, value)

    await _create_audit(
        session,
        user=current_user,
        action="application_update",
        application=app,
        old_val=old_val,
        # В журнале достаточно перечня изменённых полей. Значения адреса,
        # контактов и подписанта уже хранятся в самой заявке и не должны
        # дублироваться в долговечном аудите.
        new_val={"changed_fields": sorted(update_values)},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(app)
    return ApplicationResponse.model_validate(app)


@router.get("/{application_id}/data-confirmation")
async def get_data_confirmation(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    return await data_confirmation_state(session, app)


@router.post("/{application_id}/data-confirmation", status_code=status.HTTP_201_CREATED)
async def confirm_application_data(
    application_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=app.id,
            action="application.data.confirmed",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(app.id),
            new_value_json={"confirmed": True},
            ip_address=_get_client_ip(request),
        )
    )
    await session.flush()
    return await data_confirmation_state(session, app)


@router.post("/{application_id}/suggest-mark-language")
async def suggest_mark_language(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | None]:
    """Предложить транслитерацию и перевод обозначения."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    text = (app.mark_text or app.mark_name or "").strip()
    variants = await QueryVariantGenerator(_get_llm_provider()).build(text)
    result = {
        "transliteration": next(
            (item.text for item in variants if item.kind == "transliteration"), None
        ),
        "translation": next(
            (item.text for item in variants if item.kind == "translation"), None
        ),
    }
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=app.id,
            action="application.mark_language.suggested",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(app.id),
            new_value_json=result,
        )
    )
    await session.flush()
    return result


@router.post("/{application_id}/generate-mark-description")
async def generate_mark_description(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Подготовить описание и цвета по фактически загруженному изображению знака."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    if app.mark_type is None or app.mark_type.value not in {"figurative", "combined"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Анализ изображения доступен для изобразительного и комбинированного обозначения.",
        )
    original = await load_mark_image_content(session, app)
    if not original:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сначала загрузите изображение обозначения.",
        )
    provider = _get_llm_provider()
    generate = getattr(provider, "generate_image_structured", None)
    if not callable(generate):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI-анализ изображения недоступен для настроенной модели.",
        )
    image, mime_type = prepare_vision_image(original)
    try:
        raw = await generate(
            image=image,
            mime_type=mime_type,
            prompt=build_mark_description_prompt(
                mark_type=app.mark_type.value,
                known_text=(app.mark_text or app.mark_name or ""),
            ),
            output_schema=DESCRIPTION_SCHEMA,
            model=settings.VISION_MODEL or settings.LLM_MODEL,
        )
        description, colors = normalize_mark_description(raw)
        transliteration, translation = normalize_mark_language(raw)
    except Exception as exc:  # внешний AI не должен отдавать техническую ошибку клиенту
        logger.warning(
            "Не удалось подготовить описание изображения",
            application_id=application_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось проанализировать изображение. Попробуйте ещё раз позже или заполните описание вручную.",
        ) from exc
    result = {
        "description": description,
        "colors": colors,
        "transliteration": transliteration,
        "translation": translation,
        "model": settings.VISION_MODEL or settings.LLM_MODEL,
        "requires_confirmation": True,
    }
    # Значения сохраняются в аудите как предложения, а не как подтверждённые
    # поля заявления. Источник показывается «система» только пока текущее поле
    # в точности совпадает с этим результатом; ручная правка меняет источник.
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=app.id,
            action="application.mark_description.suggested",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(app.id),
            new_value_json={
                "description": description,
                "colors": colors,
                "transliteration": transliteration,
                "translation": translation,
            },
        )
    )
    await session.flush()
    return result


@router.post("/{application_id}/mark-details-suggestions", status_code=status.HTTP_204_NO_CONTENT)
async def record_mark_details_suggestions(
    application_id: int,
    payload: MarkDetailsSuggestionRecord,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Зафиксировать происхождение итоговых подсказок клиентского интерфейса.

    Endpoint не изменяет заявление. Он нужен, чтобы после сохранения отличить
    нетронутое автоматическое предложение от значения, которое пользователь
    отредактировал вручную.
    """
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    values = payload.model_dump(exclude_none=True)
    if not values:
        return
    session.add(
        AuditLog(
            user_id=current_user.id,
            application_id=app.id,
            action="application.mark_details.suggested",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(app.id),
            new_value_json=values,
        )
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Validation / Completeness
# ---------------------------------------------------------------------------


@router.post("/{application_id}/validate", response_model=ApplicationValidationResult)
async def validate_application(
    application_id: int,
    stage: ApplicationStage = Query(default=ApplicationStage.intake),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApplicationValidationResult:
    """Run completeness engine against the application for the given stage."""
    app = await _get_app_or_404(application_id, session, load_client=True)
    _ensure_access(app, current_user)

    completeness = _completeness_engine.validate(app, stage)

    return ApplicationValidationResult(
        is_complete=completeness.is_complete,
        blocking_issues=[
            ValidationIssue(
                field=i.field,
                message=i.message,
                severity=i.severity,
                stage=i.stage,
            )
            for i in completeness.blocking_issues
        ],
        non_blocking_issues=[
            ValidationIssue(
                field=i.field,
                message=i.message,
                severity=i.severity,
                stage=i.stage,
            )
            for i in completeness.non_blocking_issues
        ],
        requested_from=completeness.requested_from,
        recommended_message=completeness.recommended_message,
        stage=completeness.stage,
    )


@router.post("/{application_id}/request-missing-info", response_model=ApplicationValidationResult)
async def request_missing_info(
    application_id: int,
    stage: ApplicationStage = Query(default=ApplicationStage.intake),
    request: Request = None,  # type: ignore[assignment]
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer", "manager")),
) -> ApplicationValidationResult:
    """Generate a missing-info report and mark the application as info_requested."""
    app = await _get_app_or_404(application_id, session, load_client=True)
    completeness = _completeness_engine.validate(app, stage)

    if not completeness.is_complete:
        sm = ApplicationStateMachine(session)
        try:
            await sm.transition(
                app,
                new_status=ApplicationStatus.info_requested,
                user=current_user,
                reason=completeness.recommended_message,
                ip_address=_get_client_ip(request) if request else None,
            )
        except Exception:
            # Already in info_requested or transition not allowed — ignore
            pass
        await session.flush()

    return ApplicationValidationResult(
        is_complete=completeness.is_complete,
        blocking_issues=[
            ValidationIssue(field=i.field, message=i.message, severity=i.severity, stage=i.stage)
            for i in completeness.blocking_issues
        ],
        non_blocking_issues=[
            ValidationIssue(field=i.field, message=i.message, severity=i.severity, stage=i.stage)
            for i in completeness.non_blocking_issues
        ],
        requested_from=completeness.requested_from,
        recommended_message=completeness.recommended_message,
        stage=completeness.stage,
    )


# ---------------------------------------------------------------------------
# Legal Review
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/legal-review/run",
    response_model=LegalReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_legal_review(
    application_id: int,
    payload: LegalReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> LegalReviewResponse:
    """Trigger a legal review agent run for an application."""
    app = await _get_app_or_404(application_id, session)

    # Create a LegalReview record
    review = LegalReview(
        application_id=application_id,
        review_type=payload.review_type,
    )
    session.add(review)
    await session.flush()

    # Record agent run
    agent_run = AgentRun(
        application_id=application_id,
        agent_type=f"legal.{payload.review_type.value}",
        status=AgentRunStatus.started,
        input_json={
            "application_id": application_id,
            "review_type": payload.review_type.value,
            "force_refresh": payload.force_refresh,
        },
        started_at=datetime.now(timezone.utc),
    )
    session.add(agent_run)

    # Run the agent synchronously
    try:
        from app.agents.legal import AbsoluteGroundsAgent, RelativeGroundsAgent
        llm = _get_llm_provider()
        registry = _get_prompt_registry()

        input_data: dict[str, Any] = {
            "mark_text": app.mark_text or app.mark_name or "",
            "mark_type": app.mark_type.value if app.mark_type else "unknown",
            "classes_with_description": [],
            "applicant_name": None,
        }

        if payload.review_type.value in ("absolute", "combined"):
            agent = AbsoluteGroundsAgent(registry, llm)
            output = await agent.run(input_data, application_id=str(application_id))
            review.absolute_grounds_summary = output.summary
            review.confidence_score = output.confidence
            review.evidence_json = output.evidence

        if payload.review_type.value in ("relative", "combined"):
            agent = RelativeGroundsAgent(registry, llm)
            output = await agent.run(input_data, application_id=str(application_id))
            review.relative_grounds_summary = output.summary
            if not review.confidence_score:
                review.confidence_score = output.confidence

        agent_run.status = AgentRunStatus.completed
        agent_run.completed_at = datetime.now(timezone.utc)
        agent_run.output_json = {"summary": review.absolute_grounds_summary or review.relative_grounds_summary}

    except Exception as exc:
        agent_run.status = AgentRunStatus.failed
        agent_run.error_message = str(exc)
        agent_run.completed_at = datetime.now(timezone.utc)
        review.absolute_grounds_summary = f"Agent error: {exc}"

    await _create_audit(
        session,
        user=current_user,
        action="legal_review_run",
        application=app,
        new_val={"review_type": payload.review_type.value},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(review)
    return LegalReviewResponse.model_validate(review)


@router.get("/{application_id}/legal-review", response_model=LegalReviewResponse)
async def get_legal_review(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> LegalReviewResponse:
    """Get the latest legal review for an application."""
    result = await session.execute(
        select(LegalReview)
        .options(selectinload(LegalReview.findings))
        .where(LegalReview.application_id == application_id)
        .order_by(LegalReview.created_at.desc())
    )
    review = result.scalars().first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No legal review found for this application",
        )
    return LegalReviewResponse.model_validate(review)


# ---------------------------------------------------------------------------
# Classification / Nice Classes
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/classes/suggest",
    response_model=ClassSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def suggest_classes(
    application_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> ClassSuggestionResponse:
    """Trigger the Nice classification agent and persist suggestions."""
    app = await _get_app_or_404(application_id, session)

    agent_run = AgentRun(
        application_id=application_id,
        agent_type="classification.nice_classifier",
        status=AgentRunStatus.started,
        started_at=datetime.now(timezone.utc),
    )
    session.add(agent_run)

    suggestions: list[NiceClassSuggestion] = []
    summary: str | None = None
    confidence: float | None = None

    try:
        from app.agents.classification import NiceClassificationAgent
        llm = _get_llm_provider()
        registry = _get_prompt_registry()
        agent = NiceClassificationAgent(registry, llm)

        goods_services = []
        if app.goods_services_raw:
            goods_services = [
                s.strip()
                for s in app.goods_services_raw.replace("\n", ";").split(";")
                if s.strip()
            ]

        input_data = {
            "business_description": app.business_description or "",
            "goods_services": goods_services,
        }
        output = await agent.run(input_data, application_id=str(application_id))
        summary = output.summary
        confidence = output.confidence

        # Persist suggestions from findings
        primary_classes: list[int] = output.findings.get("primary_classes", [])
        for cls_num in primary_classes:
            if isinstance(cls_num, int) and 1 <= cls_num <= 45:
                sug = NiceClassSuggestion(
                    application_id=application_id,
                    class_number=cls_num,
                    rationale=output.summary,
                    confidence=output.confidence,
                )
                session.add(sug)
                suggestions.append(sug)

        agent_run.status = AgentRunStatus.completed
        agent_run.output_json = output.to_dict()
        agent_run.completed_at = datetime.now(timezone.utc)

    except Exception as exc:
        agent_run.status = AgentRunStatus.failed
        agent_run.error_message = str(exc)
        agent_run.completed_at = datetime.now(timezone.utc)

    await _create_audit(
        session,
        user=current_user,
        action="classification_suggest",
        application=app,
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    for sug in suggestions:
        await session.refresh(sug)

    suggestion_responses = [NiceClassSuggestionResponse.model_validate(s) for s in suggestions]
    return ClassSuggestionResponse(
        application_id=application_id,
        suggestions=suggestion_responses,
        summary=summary,
        confidence=confidence,
    )


@router.get("/{application_id}/classes", response_model=ClassSuggestionResponse)
async def get_classes(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClassSuggestionResponse:
    """Get all class suggestions for an application."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    result = await session.execute(
        select(NiceClassSuggestion).where(NiceClassSuggestion.application_id == application_id)
    )
    suggestions = result.scalars().all()
    return ClassSuggestionResponse(
        application_id=application_id,
        suggestions=[NiceClassSuggestionResponse.model_validate(s) for s in suggestions],
    )


@router.post(
    "/{application_id}/classes",
    response_model=NiceClassSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить класс МКТУ вручную",
)
async def add_class(
    application_id: int,
    payload: ManualClassRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> NiceClassSuggestionResponse:
    """Добавить класс, которого система не предложила.

    Класс, внесённый специалистом, сразу считается подтверждённым:
    это его собственное решение, а не предложение для проверки.
    """
    app = await _get_app_or_404(application_id, session)

    existing = (
        await session.execute(
            select(NiceClassSuggestion).where(
                NiceClassSuggestion.application_id == application_id,
                NiceClassSuggestion.class_number == payload.class_number,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Класс {payload.class_number} уже есть в деле",
        )

    suggestion = NiceClassSuggestion(
        application_id=application_id,
        class_number=payload.class_number,
        class_description=payload.class_description,
        rationale=payload.rationale or "Добавлен специалистом вручную",
        approved=True,
        approved_by=current_user.id,
    )
    session.add(suggestion)
    await session.flush()

    await _create_audit(
        session,
        user=current_user,
        action="class_added_manually",
        application=app,
        new_val={"class_number": payload.class_number},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(suggestion)
    return NiceClassSuggestionResponse.model_validate(suggestion)


@router.delete(
    "/{application_id}/classes/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить класс из дела",
)
async def delete_class(
    application_id: int,
    class_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> None:
    """Убрать класс из перечня."""
    suggestion = (
        await session.execute(
            select(NiceClassSuggestion).where(
                NiceClassSuggestion.id == class_id,
                NiceClassSuggestion.application_id == application_id,
            )
        )
    ).scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Класс не найден"
        )

    app = await _get_app_or_404(application_id, session)
    await session.delete(suggestion)
    await _create_audit(
        session,
        user=current_user,
        action="class_deleted",
        application=app,
        old_val={"class_number": suggestion.class_number},
        ip_address=_get_client_ip(request),
    )
    await session.flush()


@router.put(
    "/{application_id}/classes/{class_id}/approve",
    response_model=NiceClassSuggestionResponse,
)
async def approve_class(
    application_id: int,
    class_id: int,
    payload: ClassApprovalRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> NiceClassSuggestionResponse:
    """Lawyer approves or rejects a class suggestion."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    if current_user.role not in {UserRole.admin, UserRole.lawyer, UserRole.client}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    result = await session.execute(
        select(NiceClassSuggestion).where(
            NiceClassSuggestion.id == class_id,
            NiceClassSuggestion.application_id == application_id,
        )
    )
    sug = result.scalar_one_or_none()
    if not sug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class suggestion not found"
        )

    sug.approved = payload.approved
    sug.approved_by = current_user.id
    if payload.class_description is not None:
        sug.class_description = payload.class_description.strip() or None
    if payload.override_class is not None:
        sug.class_number = payload.override_class

    app = await _get_app_or_404(application_id, session)
    await _create_audit(
        session,
        user=current_user,
        action="class_approve" if payload.approved else "class_reject",
        application=app,
        new_val={
            "class_id": class_id,
            "approved": payload.approved,
            "class_description": sug.class_description,
        },
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(sug)
    return NiceClassSuggestionResponse.model_validate(sug)


# ---------------------------------------------------------------------------
# Conflict Search
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/conflicts/search",
    response_model=ConflictSearchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def search_conflicts(
    application_id: int,
    payload: ConflictSearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> ConflictSearchResponse:
    """Trigger conflict search via the orchestrator agent."""
    app = await _get_app_or_404(application_id, session)

    job = ConflictSearchJob(
        application_id=application_id,
        status=SearchJobStatus.running,
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.flush()

    results: list[ConflictSearchResult] = []

    try:
        from app.agents.conflicts import ConflictSearchOrchestrator
        from app.infrastructure.providers.factory import ProviderFactory
        llm = _get_llm_provider()
        registry = _get_prompt_registry()
        provider = _get_registry_provider()

        orchestrator = ConflictSearchOrchestrator(registry, llm, provider=provider)  # type: ignore[call-arg]

        input_data = {
            "queries": [{"type": "exact", "value": app.mark_text or app.mark_name or ""}],
            "classes": [],
        }
        output = await orchestrator.run(input_data, application_id=str(application_id))

        conflict_records: list[dict] = output.findings.get("conflicts", [])
        for rec in conflict_records:
            cr = ConflictSearchResult(
                search_job_id=job.id,
                application_id=application_id,
                provider=rec.get("provider", "fips"),
                source_record_id=rec.get("record_id"),
                matched_mark=rec.get("mark_text"),
                owner=rec.get("owner"),
                classes=rec.get("classes"),
                status=rec.get("status"),
                similarity_score=rec.get("similarity_score"),
            )
            session.add(cr)
            results.append(cr)

        job.status = SearchJobStatus.completed
        job.total_results = len(results)
        job.completed_at = datetime.now(timezone.utc)

    except Exception as exc:
        job.status = SearchJobStatus.failed
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)

    await _create_audit(
        session,
        user=current_user,
        action="conflict_search",
        application=app,
        new_val={"providers": payload.providers},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(job)

    from app.schemas.conflicts import ConflictSearchJobResponse, ConflictSearchResultResponse
    return ConflictSearchResponse(
        application_id=application_id,
        job=ConflictSearchJobResponse.model_validate(job),
        results=[ConflictSearchResultResponse.model_validate(r) for r in results],
        total_conflicts=sum(
            1 for r in results if r.reviewer_decision == ConflictDecision.conflict
        ),
        total_no_conflicts=sum(
            1 for r in results if r.reviewer_decision == ConflictDecision.no_conflict
        ),
        total_needs_review=sum(
            1 for r in results if r.reviewer_decision is None
        ),
    )


@router.get("/{application_id}/conflicts", response_model=ConflictSearchResponse)
async def get_conflicts(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> ConflictSearchResponse:
    """Get the latest conflict search results for an application."""
    job_result = await session.execute(
        select(ConflictSearchJob)
        .where(ConflictSearchJob.application_id == application_id)
        .order_by(ConflictSearchJob.id.desc())
    )
    job = job_result.scalars().first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conflict search found for this application",
        )

    results_result = await session.execute(
        select(ConflictSearchResult).where(
            ConflictSearchResult.search_job_id == job.id
        )
    )
    results = results_result.scalars().all()

    from app.schemas.conflicts import ConflictSearchJobResponse, ConflictSearchResultResponse
    return ConflictSearchResponse(
        application_id=application_id,
        job=ConflictSearchJobResponse.model_validate(job),
        results=[ConflictSearchResultResponse.model_validate(r) for r in results],
        total_conflicts=sum(
            1 for r in results if r.reviewer_decision == ConflictDecision.conflict
        ),
        total_no_conflicts=sum(
            1 for r in results if r.reviewer_decision == ConflictDecision.no_conflict
        ),
        total_needs_review=sum(1 for r in results if r.reviewer_decision is None),
    )


@router.put(
    "/{application_id}/conflicts/{result_id}/review",
    response_model=MessageResponse,
)
async def review_conflict(
    application_id: int,
    result_id: int,
    payload: ConflictReviewDecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> MessageResponse:
    """Lawyer records their decision on a conflict search result."""
    result = await session.execute(
        select(ConflictSearchResult).where(
            ConflictSearchResult.id == result_id,
            ConflictSearchResult.application_id == application_id,
        )
    )
    conflict_result = result.scalar_one_or_none()
    if not conflict_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conflict result not found"
        )

    conflict_result.reviewer_decision = payload.decision

    app = await _get_app_or_404(application_id, session)
    await _create_audit(
        session,
        user=current_user,
        action="conflict_review",
        application=app,
        new_val={"result_id": result_id, "decision": payload.decision.value},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    return MessageResponse(message="Conflict decision recorded")


# ---------------------------------------------------------------------------
# Recommendation Memo
# ---------------------------------------------------------------------------


@router.get("/{application_id}/recommendation")
async def get_recommendation(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the latest recommendation memo for an application."""
    app = await _get_app_or_404(application_id, session)
    _ensure_access(app, current_user)
    result = await session.execute(
        select(RecommendationMemo)
        .where(RecommendationMemo.application_id == application_id)
        .order_by(RecommendationMemo.id.desc())
    )
    memo = result.scalars().first()
    if not memo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recommendation memo found for this application",
        )
    return {
        "id": memo.id,
        "application_id": memo.application_id,
        "summary": memo.summary,
        "risk_assessment": memo.risk_assessment,
        "recommended_action": memo.recommended_action.value if memo.recommended_action else None,
        "recommended_classes_json": memo.recommended_classes_json,
        "key_conflicts_json": memo.key_conflicts_json,
        "key_risks_json": memo.key_risks_json,
        "confidence": memo.confidence,
        "approved_by": memo.approved_by,
        "approved_at": memo.approved_at.isoformat() if memo.approved_at else None,
    }


# ---------------------------------------------------------------------------
# Document Generation / Approval
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/documents/generate",
    response_model=DocumentPackageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_documents(
    application_id: int,
    payload: DocumentGenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> DocumentPackageResponse:
    """Trigger document package generation for an application."""
    app = await _get_app_or_404(application_id, session, load_client=True)

    # Verify template exists
    tmpl_result = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.id == payload.template_id)
    )
    if not tmpl_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document template not found"
        )

    pkg = DocumentPackage(
        application_id=application_id,
        template_id=payload.template_id,
        generation_status=GenerationStatus.generating,
    )
    session.add(pkg)
    await session.flush()

    agent_run = AgentRun(
        application_id=application_id,
        agent_type="documents.assembler",
        status=AgentRunStatus.started,
        started_at=datetime.now(timezone.utc),
    )
    session.add(agent_run)

    try:
        from app.agents.documents.assembler import DocumentAssemblerAgent
        llm = _get_llm_provider()
        registry = _get_prompt_registry()
        agent = DocumentAssemblerAgent(registry, llm)

        input_data: dict[str, Any] = {
            "application_id": application_id,
            "template_id": payload.template_id,
            "additional_context": payload.additional_context or {},
        }
        output = await agent.run(input_data, application_id=str(application_id))

        pkg.generation_status = GenerationStatus.generated
        pkg.file_path = output.findings.get("file_path")
        pkg.completeness_check_result_json = output.to_dict()
        agent_run.status = AgentRunStatus.completed

    except Exception as exc:
        pkg.generation_status = GenerationStatus.failed
        agent_run.status = AgentRunStatus.failed
        agent_run.error_message = str(exc)

    agent_run.completed_at = datetime.now(timezone.utc)

    await _create_audit(
        session,
        user=current_user,
        action="document_generate",
        application=app,
        new_val={"template_id": payload.template_id},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(pkg)
    return DocumentPackageResponse.model_validate(pkg)


@router.get("/{application_id}/documents", response_model=DocumentPackageListResponse)
async def get_documents(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> DocumentPackageListResponse:
    """Get all document packages for an application."""
    result = await session.execute(
        select(DocumentPackage)
        .where(DocumentPackage.application_id == application_id)
        .order_by(DocumentPackage.id.desc())
    )
    packages = result.scalars().all()
    return DocumentPackageListResponse(
        application_id=application_id,
        packages=[DocumentPackageResponse.model_validate(p) for p in packages],
    )


@router.post("/{application_id}/documents/approve", response_model=DocumentPackageResponse)
async def approve_documents(
    application_id: int,
    payload: DocumentApprovalRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer")),
) -> DocumentPackageResponse:
    """Lawyer approves a generated document package."""
    result = await session.execute(
        select(DocumentPackage).where(
            DocumentPackage.id == payload.package_id,
            DocumentPackage.application_id == application_id,
        )
    )
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document package not found"
        )

    pkg.approved_by = current_user.id
    pkg.approved_at = datetime.now(timezone.utc)

    app = await _get_app_or_404(application_id, session)
    await _create_audit(
        session,
        user=current_user,
        action="document_approve",
        application=app,
        new_val={"package_id": payload.package_id, "notes": payload.notes},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(pkg)
    return DocumentPackageResponse.model_validate(pkg)


# ---------------------------------------------------------------------------
# Submission to FIPS
# ---------------------------------------------------------------------------


@router.post("/{application_id}/submit", response_model=MessageResponse)
async def submit_to_fips(
    application_id: int,
    request: Request,
    confirm: bool = Query(
        default=False,
        description="Явное подтверждение специалистом необратимого действия",
    ),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "lawyer", "manager")),
) -> MessageResponse:
    """Подать заявку во внешний реестр через провайдера.

    Действие юридически значимое и по умолчанию запрещено.
    Требуется одновременно:
      - ENABLE_REAL_SUBMISSION=true;
      - выключенный DEMO_MODE;
      - подтверждение специалистом (confirm=true).
    """
    from app.core.config import settings

    if settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Система работает в демонстрационном режиме: реальная подача "
                "заявки запрещена. Отключите DEMO_MODE, чтобы разрешить её."
            ),
        )
    if not settings.ENABLE_REAL_SUBMISSION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Подача заявки отключена. Включите ENABLE_REAL_SUBMISSION "
                "после проверки готовности пакета документов."
            ),
        )
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Подача заявки — необратимое действие. Повторите запрос "
                "с параметром confirm=true, подтверждая осознанность."
            ),
        )

    app = await _get_app_or_404(application_id, session, load_client=True)

    # Basic completeness check for submission
    completeness = _completeness_engine.validate(app, ApplicationStage.submission)
    if not completeness.is_complete:
        blocking_msgs = "; ".join(i.message for i in completeness.blocking_issues)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Application is not ready for submission: {blocking_msgs}",
        )

    try:
        from app.infrastructure.providers.factory import ProviderFactory
        from app.infrastructure.providers.base import SubmissionPayload
        provider = _get_registry_provider()

        sub_payload = SubmissionPayload(
            application_id=str(application_id),
            mark_text=app.mark_text or app.mark_name or "",
            mark_type=app.mark_type.value if app.mark_type else "unknown",
            applicant_name=app.client.full_name_or_company_name if app.client else "",
            goods_services=app.goods_services_raw or "",
            classes=[],
        )
        result = await provider.submit(sub_payload)

        submission = Submission(
            application_id=application_id,
            provider="fips",
            external_submission_id=result.external_id,
            submitted_at=datetime.now(timezone.utc),
            current_status=result.status,
        )
        session.add(submission)
        await session.flush()

        event = SubmissionStatusEvent(
            submission_id=submission.id,
            previous_status=None,
            new_status=result.status or "submitted",
        )
        session.add(event)

        # Transition application
        sm = ApplicationStateMachine(session)
        await sm.transition(
            app,
            new_status=ApplicationStatus.submitted,
            user=current_user,
            ip_address=_get_client_ip(request),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Submission to FIPS failed: {exc}",
        ) from exc

    await _create_audit(
        session,
        user=current_user,
        action="submit_fips",
        application=app,
        new_val={"status": "submitted"},
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    return MessageResponse(message="Application submitted to FIPS successfully")


@router.get("/{application_id}/status")
async def get_application_status(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current status, submission record, and status event history."""
    app = await _get_app_or_404(application_id, session)

    sub_result = await session.execute(
        select(Submission)
        .where(Submission.application_id == application_id)
        .order_by(Submission.id.desc())
    )
    submission = sub_result.scalars().first()

    events: list[dict[str, Any]] = []
    if submission:
        events_result = await session.execute(
            select(SubmissionStatusEvent)
            .where(SubmissionStatusEvent.submission_id == submission.id)
            .order_by(SubmissionStatusEvent.occurred_at)
        )
        for ev in events_result.scalars().all():
            events.append(
                {
                    "id": ev.id,
                    "previous_status": ev.previous_status,
                    "new_status": ev.new_status,
                    "occurred_at": ev.occurred_at.isoformat(),
                    "notification_sent": ev.notification_sent,
                }
            )

    sm = ApplicationStateMachine(session)
    allowed = [s.value for s in sm.allowed_transitions(app.status)]

    return {
        "application_id": application_id,
        "status": app.status.value,
        "allowed_transitions": allowed,
        "submission": {
            "id": submission.id,
            "provider": submission.provider,
            "external_id": submission.external_submission_id,
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "current_status": submission.current_status,
        }
        if submission
        else None,
        "status_events": events,
    }


# ---------------------------------------------------------------------------
# State transition
# ---------------------------------------------------------------------------


@router.post("/{application_id}/transition", response_model=ApplicationResponse)
async def transition_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApplicationResponse:
    """Transition an application to a new status (validates via state machine)."""
    app = await _get_app_or_404(application_id, session)

    sm = ApplicationStateMachine(session)
    await sm.transition(
        app,
        new_status=payload.new_status,
        user=current_user,
        reason=payload.reason,
        ip_address=_get_client_ip(request),
    )
    await session.flush()
    await session.refresh(app)
    return ApplicationResponse.model_validate(app)
