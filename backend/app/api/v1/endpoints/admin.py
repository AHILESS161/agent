"""Admin endpoints — prompts, models, jobs, system stats."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.infrastructure.database.models import (
    AgentRun,
    AgentRunStatus,
    AuditLog,
    BackgroundJob,
    Client,
    ConflictSearchResult,
    DocumentPackage,
    JobStatus,
    LegalReview,
    NiceClassSuggestion,
    PromptDefinition,
    Submission,
    TrademarkApplicationDraft,
    User,
)
from app.infrastructure.database.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_prompt(p: PromptDefinition) -> dict[str, Any]:
    return {
        "id": p.id,
        "prompt_id": p.prompt_id,
        "version": p.version,
        "description": p.description,
        "system_prompt": p.system_prompt,
        "user_template": p.user_template,
        "input_schema_json": p.input_schema_json,
        "output_schema_json": p.output_schema_json,
        "examples_json": p.examples_json,
        "guardrails_json": p.guardrails_json,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
    }


def _serialize_job(j: BackgroundJob) -> dict[str, Any]:
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status.value,
        "payload_json": j.payload_json,
        "result_json": j.result_json,
        "error_message": j.error_message,
        "retry_count": j.retry_count,
        "max_retries": j.max_retries,
        "created_at": j.created_at.isoformat(),
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@router.get("/prompts")
async def list_prompts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    is_active: Optional[bool] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """List all prompt definitions."""
    base_q = select(PromptDefinition)
    if is_active is not None:
        base_q = base_q.where(PromptDefinition.is_active == is_active)

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        base_q.order_by(PromptDefinition.id).offset(offset).limit(page_size)
    )
    prompts = result.scalars().all()
    total_pages = max(1, (total + page_size - 1) // page_size)

    # Also fetch prompts from the in-memory PromptRegistry for a unified view
    try:
        from app.infrastructure.llm.prompt_registry import PromptRegistry
        registry = PromptRegistry()
        registry_prompts = [
            {
                "prompt_id": pid,
                "source": "registry",
            }
            for pid in registry.list_ids()  # type: ignore[attr-defined]
        ]
    except Exception:
        registry_prompts = []

    return {
        "items": [_serialize_prompt(p) for p in prompts],
        "registry_prompts": registry_prompts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """Get a prompt by its string prompt_id."""
    # Try DB first
    result = await session.execute(
        select(PromptDefinition).where(PromptDefinition.prompt_id == prompt_id)
    )
    prompt = result.scalar_one_or_none()
    if prompt:
        return _serialize_prompt(prompt)

    # Fall back to in-memory registry
    try:
        from app.infrastructure.llm.prompt_registry import PromptRegistry
        registry = PromptRegistry()
        defn = registry.get(prompt_id)
        return {
            "prompt_id": prompt_id,
            "source": "registry",
            "system_prompt": defn.system,
            "user_template": defn.user_template if hasattr(defn, "user_template") else None,
            "output_schema_json": defn.output_schema if hasattr(defn, "output_schema") else None,
        }
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Prompt '{prompt_id}' not found",
    )


# ---------------------------------------------------------------------------
# LLM Models
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(
    _current_user: User = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """List configured LLM model(s) from application settings."""
    from app.core.config import settings
    return {
        "configured": [
            {
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "base_url": settings.LLM_BASE_URL,
                "api_key_set": bool(
                    settings.LLM_API_KEY or settings.GIGACHAT_AUTHORIZATION_KEY
                ),
            }
        ]
    }


# ---------------------------------------------------------------------------
# Background Jobs
# ---------------------------------------------------------------------------


@router.get("/jobs")
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    job_status: Optional[JobStatus] = Query(default=None, alias="status"),
    job_type: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """List background jobs with optional filters."""
    base_q = select(BackgroundJob)
    if job_status is not None:
        base_q = base_q.where(BackgroundJob.status == job_status)
    if job_type:
        base_q = base_q.where(BackgroundJob.job_type == job_type)

    total_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        base_q.order_by(BackgroundJob.created_at.desc()).offset(offset).limit(page_size)
    )
    jobs = result.scalars().all()
    total_pages = max(1, (total + page_size - 1) // page_size)

    return {
        "items": [_serialize_job(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ---------------------------------------------------------------------------
# System Statistics
# ---------------------------------------------------------------------------


@router.get("/stats")
async def system_stats(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """Return aggregate system statistics."""

    async def _count(model: Any, *filters: Any) -> int:
        q = select(func.count()).select_from(model)
        if filters:
            for f in filters:
                q = q.where(f)
        result = await session.execute(q)
        return result.scalar_one()

    total_users = await _count(User)
    active_users = await _count(User, User.is_active == True)  # noqa: E712
    total_clients = await _count(Client)
    total_applications = await _count(TrademarkApplicationDraft)
    submitted_applications = await _count(
        TrademarkApplicationDraft,
        TrademarkApplicationDraft.status == "submitted",
    )
    draft_applications = await _count(
        TrademarkApplicationDraft,
        TrademarkApplicationDraft.status == "draft",
    )

    total_legal_reviews = await _count(LegalReview)
    total_conflict_results = await _count(ConflictSearchResult)
    total_class_suggestions = await _count(NiceClassSuggestion)
    total_document_packages = await _count(DocumentPackage)
    total_submissions = await _count(Submission)

    # Agent run stats
    total_agent_runs = await _count(AgentRun)
    failed_agent_runs = await _count(AgentRun, AgentRun.status == AgentRunStatus.failed)
    completed_agent_runs = await _count(AgentRun, AgentRun.status == AgentRunStatus.completed)

    # Audit log stats
    total_audit_logs = await _count(AuditLog)

    # Background job stats
    total_jobs = await _count(BackgroundJob)
    failed_jobs = await _count(BackgroundJob, BackgroundJob.status == JobStatus.failed)
    pending_jobs = await _count(BackgroundJob, BackgroundJob.status == JobStatus.queued)

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "inactive": total_users - active_users,
        },
        "clients": {"total": total_clients},
        "applications": {
            "total": total_applications,
            "draft": draft_applications,
            "submitted": submitted_applications,
            "in_progress": total_applications - draft_applications - submitted_applications,
        },
        "legal_reviews": {"total": total_legal_reviews},
        "conflict_results": {"total": total_conflict_results},
        "class_suggestions": {"total": total_class_suggestions},
        "document_packages": {"total": total_document_packages},
        "submissions": {"total": total_submissions},
        "agent_runs": {
            "total": total_agent_runs,
            "completed": completed_agent_runs,
            "failed": failed_agent_runs,
        },
        "background_jobs": {
            "total": total_jobs,
            "pending": pending_jobs,
            "failed": failed_jobs,
        },
        "audit_logs": {"total": total_audit_logs},
    }
