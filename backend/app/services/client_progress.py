"""Одинаковое фактическое состояние для списка и карточки заявки."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    BackgroundJob, NiceClassSuggestion, RiskAssessment, RiskFinding,
)


def project_progress(status, *, has_classes=False, job_status=None,
                     job_result=None, assessments=()):
    status = getattr(status, "value", status)
    job_status = getattr(job_status, "value", job_status)
    if status in {"closed", "submitted"}:
        state, step = status, 4
    elif job_status in {"queued", "retrying", "running"}:
        state, step = ("queued" if job_status == "queued" else "analyzing"), 3
    elif job_status in {"failed", "cancelled"}:
        state, step = "failed", 3
    elif status in {"document_generation", "document_approved"}:
        state, step = "documents", 4
    elif job_status == "waiting_human_review" or any(assessments) or (
        job_status == "completed" and not (job_result or {}).get("is_complete", False)
    ):
        state, step = "incomplete", 4
    elif assessments or job_status == "completed":
        state, step = "result", 4
    elif status in {"legal_review_pending", "legal_review_in_progress",
                    "conflict_search_pending", "conflict_search_in_progress"}:
        state, step = "analyzing", 3
    elif has_classes or status.startswith("classification_"):
        state, step = "classes", 2
    else:
        state, step = "draft", 1
    return {"client_progress_step": step, "client_progress_state": state}


async def client_progress(session: AsyncSession, applications):
    ids = [app.id for app in applications]
    if not ids:
        return {}
    from app.services.class_analysis import ClassContext
    from app.services.risk_analysis import AnalysisContext
    from app.services.reviewed_risks import reviewed_view

    class_rows = (await session.scalars(select(NiceClassSuggestion)
        .where(NiceClassSuggestion.application_id.in_(ids))
        .order_by(NiceClassSuggestion.class_number))).all()
    classes = {item.application_id for item in class_rows}
    fingerprints = {}
    for app in applications:
        rows = [item for item in class_rows if item.application_id == app.id]
        context = ClassContext(approved=[r for r in rows if r.approved is True],
                               suggested=[r for r in rows if r.approved is None])
        fingerprints[app.id] = AnalysisContext.from_application(app, context).fingerprint()
    jobs = (await session.scalars(select(BackgroundJob).where(
        BackgroundJob.job_type == "full_analysis",
        BackgroundJob.payload_json["application_id"].as_integer().in_(ids),
    ).order_by(BackgroundJob.id.desc()))).all()
    latest_jobs = {}
    for job in jobs:
        latest_jobs.setdefault(int(job.payload_json["application_id"]), job)
    results = (await session.scalars(select(RiskAssessment).where(
        RiskAssessment.application_id.in_(ids)
    ).order_by(RiskAssessment.id.desc()))).all()
    latest_results = {}
    for result in results:
        latest_results.setdefault((result.application_id, result.analysis_kind), result)
    finding_rows = (await session.scalars(select(RiskFinding).where(
        RiskFinding.assessment_id.in_([r.id for r in latest_results.values()])
    ))).all() if latest_results else []
    incomplete_results = {
        key: reviewed_view(result, [f for f in finding_rows if f.assessment_id == result.id],
                           fingerprints[result.application_id])["is_inconclusive"]
        for key, result in latest_results.items()
    }
    return {app.id: project_progress(
        app.status, has_classes=app.id in classes,
        job_status=latest_jobs[app.id].status if app.id in latest_jobs else None,
        job_result=latest_jobs[app.id].result_json if app.id in latest_jobs else None,
        assessments=tuple(value for (aid, _), value in incomplete_results.items() if aid == app.id),
    ) for app in applications}
