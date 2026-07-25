"""MVP pipeline endpoint.

Запускает шаги 2→8 для заявки:
  2. Классификация по МКТУ (NiceClassificationAgent)
  3. Поиск конфликтов (ConflictSearchQueryBuilderAgent + ConflictSearchOrchestrator
     + ConflictAnalysisAgent)
  4. Правовая экспертиза (AbsoluteGroundsAgent + RelativeGroundsAgent)
  5. Рекомендация (RecommendationAgent)
  6. Документы (DocumentAssemblyAgent)
  7. Подача (SubmissionAgent) — сохраняет Submission и SubmissionStatusEvent
  8. Мониторинг статуса (StatusMonitoringAgent)

Шаг 1 (IntakeValidator/ClientDataNormalizer) уже выполнен при создании заявки,
поэтому здесь он не дублируется.

Этот эндпоинт намеренно «тупой» — он последовательно вызывает агентов и
сохраняет их выводы в БД. Для MVP этого достаточно; полноценный LangGraph-оркестратор
описан в docs/agent-graph.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.infrastructure.database.models import (
    AgentRun,
    AgentRunStatus,
    ApplicationStatus,
    ConflictDecision,
    ConflictSearchJob,
    ConflictSearchResult,
    DocumentPackage,
    DocumentTemplate,
    GenerationStatus,
    RecommendationMemo,
    SearchJobStatus,
    Submission,
    SubmissionStatusEvent,
    TemplateType,
    TrademarkApplicationDraft,
    User,
)
from app.infrastructure.database.session import get_session
from app.schemas.common import MessageResponse
from app.services.completeness_engine import ApplicationStage, CompletenessEngine

router = APIRouter(prefix="/applications", tags=["mvp-pipeline"])

_completeness_engine = CompletenessEngine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_app(session: AsyncSession, application_id: int) -> TrademarkApplicationDraft:
    result = await session.execute(
        select(TrademarkApplicationDraft).where(
            TrademarkApplicationDraft.id == application_id
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )
    return app


def _get_client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


async def _create_audit(
    session: AsyncSession,
    *,
    user: User,
    action: str,
    application: TrademarkApplicationDraft,
    new_val: dict | None = None,
    ip_address: str | None = None,
) -> None:
    from app.infrastructure.database.models import AuditLog

    session.add(
        AuditLog(
            user_id=user.id,
            application_id=application.id,
            action=action,
            entity_type="TrademarkApplicationDraft",
            entity_id=str(application.id),
            new_value_json=new_val,
            ip_address=ip_address,
        )
    )


# Провайдеры живут в app.api.dependencies — единственный источник правды.
from app.api.dependencies import (  # noqa: E402
    _get_llm_provider,
    _get_prompt_registry,
    _get_registry_provider,
)


async def _ensure_default_template(session: AsyncSession) -> DocumentTemplate:
    """Гарантируем, что в БД есть активный шаблон документа."""
    result = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.is_active.is_(True)).limit(1)
    )
    template = result.scalar_one_or_none()
    if template is not None:
        return template
    template = DocumentTemplate(
        name="Заявка на товарный знак (MVP)",
        description="Дефолтный шаблон заявки для MVP-пайплайна.",
        template_type=TemplateType.application_form,
        file_path="templates/mvp_application.docx",
        version="1.0",
        is_active=True,
        field_mapping_json={
            "mark_text": "наименование_обозначения",
            "mark_type": "тип_обозначения",
            "applicant_name": "заявитель_наименование",
            "applicant_inn": "заявитель_инн",
            "goods_services": "перечень_товаров_услуг",
            "classes": "классы_мкту",
        },
    )
    session.add(template)
    await session.flush()
    return template


async def _start_agent_run(
    session: AsyncSession,
    *,
    application_id: int,
    agent_type: str,
    input_data: dict[str, Any],
) -> AgentRun:
    run = AgentRun(
        application_id=application_id,
        agent_type=agent_type,
        status=AgentRunStatus.started,
        input_json=input_data,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()
    return run


async def _finish_agent_run(
    session: AsyncSession,
    run: AgentRun,
    *,
    summary: str,
    findings: Any,
    confidence: float | None = None,
    error: str | None = None,
) -> None:
    run.status = AgentRunStatus.completed if error is None else AgentRunStatus.failed
    run.completed_at = datetime.now(timezone.utc)
    run.output_json = {"summary": summary, "findings": findings}
    if confidence is not None:
        run.confidence_score = confidence
    if error is not None:
        run.error_message = error


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


async def _step_classification(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
) -> dict[str, Any]:
    from app.agents.classification import NiceClassificationAgent

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="classification.nice_classifier",
        input_data={
            "mark_text": app.mark_text or app.mark_name or "",
            "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
            "preliminary_goods_services": app.goods_services_raw or "",
            "business_description": app.business_description or "",
            "existing_classes": app.classes or [],
        },
    )

    agent = NiceClassificationAgent(registry, llm)
    output = await agent.run(
        {
            "mark_text": app.mark_text or app.mark_name or "",
            "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
            "preliminary_goods_services": app.goods_services_raw or "",
            "business_description": app.business_description or "",
            "existing_classes": app.classes or [],
        },
        application_id=str(app.id),
    )
    findings = output.findings or {}

    await _finish_agent_run(
        session,
        run,
        summary=output.summary,
        findings=findings,
        confidence=output.confidence,
    )

    suggested_classes: list[int] = []
    for item in findings.get("suggested_classes", []) or []:
        cls = item.get("class") if isinstance(item, dict) else None
        if cls is None and isinstance(item, dict):
            cls = item.get("class_number") or item.get("nice_class")
        if isinstance(cls, int):
            suggested_classes.append(cls)

    if suggested_classes and not app.classes:
        app.classes = sorted(set(suggested_classes))

    return {
        "agent_run_id": run.id,
        "summary": output.summary,
        "suggested_classes": suggested_classes,
        "human_review_required": output.human_review_required,
    }


async def _step_legal_review(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
) -> dict[str, Any]:
    from app.agents.legal import AbsoluteGroundsAgent, RelativeGroundsAgent

    input_data: dict[str, Any] = {
        "mark_text": app.mark_text or app.mark_name or "",
        "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
        "classes_with_description": [
            {"class": c, "description": app.goods_services_raw or ""}
            for c in (app.classes or [])
        ],
        "applicant_name": None,
    }

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="legal.combined",
        input_data=input_data,
    )

    abs_agent = AbsoluteGroundsAgent(registry, llm)
    rel_agent = RelativeGroundsAgent(registry, llm)
    abs_out = await abs_agent.run(input_data, application_id=str(app.id))
    rel_out = await rel_agent.run(input_data, application_id=str(app.id))

    findings = {
        "absolute_grounds": abs_out.findings,
        "relative_grounds": rel_out.findings,
    }
    summary = (
        f"Абсолютные: {abs_out.summary} | "
        f"Относительные: {rel_out.summary}"
    )

    await _finish_agent_run(
        session,
        run,
        summary=summary,
        findings=findings,
        confidence=min(abs_out.confidence, rel_out.confidence),
    )

    return {
        "agent_run_id": run.id,
        "summary": summary,
        "absolute_human_review": abs_out.human_review_required,
        "relative_human_review": rel_out.human_review_required,
    }


async def _step_conflicts(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
    registry_provider: Any,
) -> dict[str, Any]:
    from app.agents.conflicts import (
        ConflictAnalysisAgent,
        ConflictSearchOrchestrator,
        ConflictSearchQueryBuilderAgent,
    )

    job = ConflictSearchJob(
        application_id=app.id,
        status=SearchJobStatus.running,
        provider="mock",
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.flush()

    builder_run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="conflicts.query_builder",
        input_data={
            "mark_text": app.mark_text or app.mark_name or "",
            "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
            "classes": app.classes or [],
        },
    )
    builder = ConflictSearchQueryBuilderAgent(registry, llm)
    builder_out = await builder.run(
        {
            "mark_text": app.mark_text or app.mark_name or "",
            "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
            "classes": app.classes or [],
        },
        application_id=str(app.id),
    )
    await _finish_agent_run(
        session,
        builder_run,
        summary=builder_out.summary,
        findings=builder_out.findings,
        confidence=builder_out.confidence,
    )
    queries = (builder_out.findings or {}).get("queries", [])
    job.search_strategy_json = {"queries": queries, "strategy": (builder_out.findings or {}).get("search_strategy")}

    orch_run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="conflicts.orchestrator",
        input_data={"queries": queries, "classes": app.classes or []},
    )
    orchestrator = ConflictSearchOrchestrator(registry, llm, registry_provider=registry_provider)
    orch_out = await orchestrator.run(
        {"queries": queries, "classes": app.classes or []},
        application_id=str(app.id),
    )
    await _finish_agent_run(
        session,
        orch_run,
        summary=orch_out.summary,
        findings=orch_out.findings,
        confidence=orch_out.confidence,
    )

    conflicts = (orch_out.findings or {}).get("conflicts", [])
    for c in conflicts:
        result = ConflictSearchResult(
            search_job_id=job.id,
            application_id=app.id,
            provider="mock",
            source_record_id=str(c.get("record_id", "")),
            matched_mark=c.get("mark_text"),
            owner=c.get("owner"),
            classes=c.get("classes"),
            status=c.get("status"),
            filing_date=c.get("filing_date"),
            registration_date=c.get("registration_date"),
            similarity_score=c.get("similarity_score"),
            reviewer_decision=ConflictDecision.pending,
        )
        session.add(result)
    job.total_results = len(conflicts)

    analyzer_run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="conflicts.analyzer",
        input_data={
            "applicant_mark": {
                "text": app.mark_text or app.mark_name or "",
                "type": (app.mark_type.value if app.mark_type else "словесное"),
                "classes": app.classes or [],
            },
            "conflicts": conflicts,
        },
    )
    analyzer = ConflictAnalysisAgent(registry, llm)
    analyzer_out = await analyzer.run(
        {
            "applicant_mark": {
                "text": app.mark_text or app.mark_name or "",
                "type": (app.mark_type.value if app.mark_type else "словесное"),
                "classes": app.classes or [],
            },
            "conflicts": conflicts,
        },
        application_id=str(app.id),
    )
    await _finish_agent_run(
        session,
        analyzer_run,
        summary=analyzer_out.summary,
        findings=analyzer_out.findings,
        confidence=analyzer_out.confidence,
    )

    job.status = SearchJobStatus.completed
    job.completed_at = datetime.now(timezone.utc)

    return {
        "job_id": job.id,
        "total_conflicts": len(conflicts),
        "summary": analyzer_out.summary,
        "risk": (analyzer_out.findings or {}).get("overall_risk"),
    }


async def _step_recommendation(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
    pipeline_context: dict[str, Any],
) -> dict[str, Any]:
    from app.agents.recommendations import RecommendationAgent

    intake_result = pipeline_context.get("intake_result", {})
    input_data: dict[str, Any] = {
        "application_id": str(app.id),
        "mark_text": app.mark_text or app.mark_name or "",
        "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
        "classes": app.classes or [],
        "applicant_name": (app.client.full_name_or_company_name if app.client else ""),
        "intake_result": intake_result,
        "absolute_grounds_result": pipeline_context.get("absolute", {}),
        "relative_grounds_result": pipeline_context.get("relative", {}),
        "classification_result": pipeline_context.get("classification", {}),
        "additional_context": "MVP автоматический прогон пайплайна",
    }

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="recommendations.recommender",
        input_data=input_data,
    )
    agent = RecommendationAgent(registry, llm)
    output = await agent.run(input_data, application_id=str(app.id))
    await _finish_agent_run(
        session,
        run,
        summary=output.summary,
        findings=output.findings,
        confidence=output.confidence,
    )

    findings = output.findings or {}
    risk = (findings.get("risk_assessment") or {}).get("overall_risk") or "medium"
    action = "submit" if findings.get("proceed_to_filing") else "human_review"
    memo = RecommendationMemo(
        application_id=app.id,
        summary=output.summary,
        risk_assessment=risk,
        recommended_action=None,
        recommended_classes_json=app.classes,
        key_conflicts_json=pipeline_context.get("conflicts", {}).get("conflicts"),
        key_risks_json=findings.get("key_findings"),
        confidence=output.confidence,
        evidence_json=output.evidence,
    )
    session.add(memo)
    await session.flush()

    return {
        "memo_id": memo.id,
        "summary": output.summary,
        "proceed": bool(findings.get("proceed_to_filing")),
        "overall_risk": risk,
        "recommended_action": action,
    }


async def _step_documents(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
) -> dict[str, Any]:
    from app.agents.documents import DocumentAssemblyAgent

    template = await _ensure_default_template(session)

    application_data: dict[str, Any] = {
        "mark_text": app.mark_text or app.mark_name or "",
        "mark_type": (app.mark_type.value if app.mark_type else "словесное"),
        "applicant_name": (app.client.full_name_or_company_name if app.client else ""),
        "applicant_inn": (app.client.inn if app.client else ""),
        "goods_services": app.goods_services_raw or "",
        "classes": app.classes or [],
    }

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="documents.assembler",
        input_data={
            "application_data": application_data,
            "template_id": template.id,
        },
    )
    agent = DocumentAssemblyAgent(registry, llm)
    output = await agent.run(
        {
            "application_data": application_data,
            "template_id": template.id,
        },
        application_id=str(app.id),
    )
    await _finish_agent_run(
        session,
        run,
        summary=output.summary,
        findings=output.findings,
        confidence=output.confidence,
    )

    pkg = DocumentPackage(
        application_id=app.id,
        template_id=template.id,
        generation_status=GenerationStatus.generated,
        completeness_check_result_json={
            "summary": output.summary,
            "findings": output.findings,
        },
        file_path=f"packages/app_{app.id}_mvp.docx",
    )
    session.add(pkg)
    await session.flush()

    return {
        "package_id": pkg.id,
        "summary": output.summary,
        "ready": True,
    }


async def _step_submission(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
    registry_provider: Any,
    request: Request,
    current_user: User,
) -> dict[str, Any]:
    from app.agents.submission import SubmissionAgent

    completeness = _completeness_engine.validate(app, ApplicationStage.submission)
    if not completeness.is_complete:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "stage": "submission",
                "blocking": [i.message for i in completeness.blocking_issues],
            },
        )

    payload_dict: dict[str, Any] = {
        "applicant_data": {
            "name": (app.client.full_name_or_company_name if app.client else ""),
            "inn": (app.client.inn if app.client else ""),
        },
        "mark_data": {
            "text": app.mark_text or app.mark_name or "",
            "type": (app.mark_type.value if app.mark_type else "словесное"),
        },
        "goods_services": [
            {"class": c, "description": app.goods_services_raw or ""}
            for c in (app.classes or [])
        ],
        "classes": app.classes or [],
        "description": app.business_description or "",
        "documents": [f"packages/app_{app.id}_mvp.docx"],
    }

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="submission.submitter",
        input_data=payload_dict,
    )
    agent = SubmissionAgent(registry, llm, registry_provider=registry_provider)
    output = await agent.run(payload_dict, application_id=str(app.id))
    await _finish_agent_run(
        session,
        run,
        summary=output.summary,
        findings=output.findings,
        confidence=output.confidence,
        error=output.error,
    )

    if not (output.findings or {}).get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "stage": "submission",
                "error": (output.findings or {}).get("error_message") or output.error or "unknown",
            },
        )

    external_id = (output.findings or {}).get("external_id")
    submission = Submission(
        application_id=app.id,
        provider="mock",
        external_submission_id=external_id,
        submitted_at=datetime.now(timezone.utc),
        current_status="submitted",
    )
    session.add(submission)
    await session.flush()

    session.add(
        SubmissionStatusEvent(
            submission_id=submission.id,
            previous_status=None,
            new_status="submitted",
            raw_payload_json={"agent_run_id": run.id},
        )
    )

        # MVP-поток намеренно обходит жёсткие переходы state machine.
    app.status = ApplicationStatus.submitted
    app.updated_at = datetime.now(timezone.utc)

    return {
        "submission_id": submission.id,
        "external_id": external_id,
        "summary": output.summary,
    }


async def _step_status_monitor(
    session: AsyncSession,
    app: TrademarkApplicationDraft,
    llm: Any,
    registry: Any,
    registry_provider: Any,
) -> dict[str, Any]:
    from app.agents.status import StatusMonitoringAgent

    result = await session.execute(
        select(Submission)
        .where(Submission.application_id == app.id)
        .order_by(Submission.id.desc())
    )
    submission = result.scalars().first()
    if submission is None or not submission.external_submission_id:
        return {"skipped": True, "reason": "no submission"}

    run = await _start_agent_run(
        session,
        application_id=app.id,
        agent_type="status.monitor",
        input_data={
            "external_id": submission.external_submission_id,
            "current_status": submission.current_status or "filed",
        },
    )
    agent = StatusMonitoringAgent(registry, llm, registry_provider=registry_provider)
    output = await agent.run(
        {
            "external_id": submission.external_submission_id,
            "current_status": submission.current_status or "filed",
        },
        application_id=str(app.id),
    )
    await _finish_agent_run(
        session,
        run,
        summary=output.summary,
        findings=output.findings,
        confidence=output.confidence,
        error=output.error,
    )

    findings = output.findings or {}
    new_status = findings.get("new_status") or submission.current_status
    if findings.get("status_changed"):
        submission.current_status = new_status
        submission.last_polled_at = datetime.now(timezone.utc)
        session.add(
            SubmissionStatusEvent(
                submission_id=submission.id,
                previous_status=findings.get("previous_status"),
                new_status=new_status,
                raw_payload_json={"agent_run_id": run.id, "details": findings.get("details")},
            )
        )

    return {
        "submission_id": submission.id,
        "status": new_status,
        "summary": output.summary,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/{application_id}/mvp-run", response_model=MessageResponse)
async def run_mvp_pipeline(
    application_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Прогон шагов 2→8 для заявки (MVP)."""
    app = await _load_app(session, application_id)

    llm = _get_llm_provider()
    registry = _get_prompt_registry()
    registry_provider = _get_registry_provider()

    steps: list[dict[str, Any]] = []

    def _record(step: str, status_: str, **fields: Any) -> None:
        steps.append({"step": step, "status": status_, **fields})

    try:
        cls = await _step_classification(session, app, llm, registry)
        _record("classification", "completed", **cls)

        legal = await _step_legal_review(session, app, llm, registry)
        _record("legal_review", "completed", **legal)

        conflicts = await _step_conflicts(session, app, llm, registry, registry_provider)
        _record("conflicts", "completed", **conflicts)

        pipeline_context: dict[str, Any] = {
            "intake_result": {"status": "ok"},
            "absolute": (legal.get("summary") or ""),
            "relative": (legal.get("summary") or ""),
            "classification": cls,
            "conflicts": conflicts,
        }
        recommendation = await _step_recommendation(session, app, llm, registry, pipeline_context)
        _record("recommendation", "completed", **recommendation)

        documents = await _step_documents(session, app, llm, registry)
        _record("documents", "completed", **documents)

        submission = await _step_submission(
            session, app, llm, registry, registry_provider, request, current_user
        )
        _record("submission", "completed", **submission)

        status_step = await _step_status_monitor(session, app, llm, registry, registry_provider)
        _record("status", "completed", **status_step)

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "steps": steps},
        ) from exc

    await _create_audit(
        session,
        user=current_user,
        action="mvp_pipeline_run",
        application=app,
        new_val={"steps": steps},
        ip_address=_get_client_ip(request),
    )
    await session.flush()

    return MessageResponse(
        message=f"MVP pipeline completed for application {application_id}; steps: {len(steps)}"
    )