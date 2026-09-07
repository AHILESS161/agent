"""Решения человека — отдельная проекция; машинный результат неизменен."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import (
    RecommendationMemo, RecommendedAction, RiskAssessment, RiskFinding,
)

ORDER = ["low", "medium", "high", "critical"]


def reviewed_view(assessment, findings, fingerprint):
    machine = assessment.overall_risk.value if assessment.overall_risk else None
    original_fingerprint = (getattr(assessment, "verification_json", None) or {}).get("input_fingerprint")
    active, decisions = [], []
    stale = bool(original_fingerprint and fingerprint and original_fingerprint != fingerprint)
    incomplete = assessment.is_inconclusive or stale
    for finding in findings:
        decision = getattr(finding.reviewer_decision, "value", finding.reviewer_decision)
        verification = finding.verification_json or {}
        valid = bool(decision and fingerprint and verification.get("review_input_fingerprint") == fingerprint)
        if decision and not valid:
            stale = True
        if valid:
            decisions.append(finding.id)
            if decision == "reject":
                continue
            if decision == "modify":
                incomplete = True
        active.append(finding)
    level = max((f.level.value for f in active), key=ORDER.index) if active else ("low" if decisions else machine)
    incomplete = incomplete or stale
    if incomplete and level == "low":
        level = None
    return {"overall_risk": level, "machine_overall_risk": machine,
        "is_inconclusive": incomplete, "review_applied": bool(decisions),
        "review_stale": stale, "active_finding_ids": [f.id for f in active]}


def reviewed_summary(assessment, findings, view):
    if view["review_stale"]:
        return "Данные заявки изменились. Предыдущие выводы и решения требуют повторной проверки."
    if not view["review_applied"]:
        return assessment.summary
    active = [f.explanation for f in findings
              if f.id in view["active_finding_ids"] and f.level.value != "low"]
    return "Результат с учётом решений специалиста. " + (
        " ".join(active) if active else "Подтверждённых препятствий в этой части проверки не осталось."
    )


async def refresh_reviewed_memo(session: AsyncSession, application):
    from app.services.class_analysis import load_class_context
    from app.services.risk_analysis import AnalysisContext
    context = await load_class_context(session, application.id)
    fingerprint = AnalysisContext.from_application(application, context).fingerprint()
    assessments = (await session.scalars(select(RiskAssessment).where(
        RiskAssessment.application_id == application.id).order_by(RiskAssessment.id.desc()))).all()
    latest = {}
    for assessment in assessments:
        latest.setdefault(assessment.analysis_kind, assessment)
    views, risks, conflicts, has_decisions = [], [], [], False
    for assessment in latest.values():
        findings = (await session.scalars(select(RiskFinding).where(RiskFinding.assessment_id == assessment.id))).all()
        has_decisions |= any(f.reviewer_decision for f in findings)
        view = reviewed_view(assessment, findings, fingerprint)
        views.append(view)
        selected = [f.explanation for f in findings if f.id in view["active_finding_ids"] and f.level.value != "low"]
        risks.extend(selected)
        if assessment.analysis_kind.value == "relative_grounds": conflicts.extend(selected)
    if not has_decisions:
        return
    memo = await session.scalar(select(RecommendationMemo).where(
        RecommendationMemo.application_id == application.id).order_by(RecommendationMemo.id.desc()).limit(1))
    if memo is None:
        return
    levels = [v["overall_risk"] for v in views if v["overall_risk"]]
    level = max(levels, key=ORDER.index) if levels else None
    incomplete = len(views) < 2 or any(v["is_inconclusive"] for v in views)
    if incomplete and level == "low": level = None
    values = {
        "summary": "Требуется дополнительная проверка." if incomplete else "Результат с учётом решений специалиста.",
        "risk_assessment": f"Текущий уровень риска: {level or 'не определён'}.",
        "key_risks_json": risks[:10],
        "key_conflicts_json": conflicts[:10],
        "recommended_action": (
            RecommendedAction.further_review if incomplete or level == "medium"
            else RecommendedAction.proceed if level == "low"
            else RecommendedAction.modify
        ),
        "evidence_json": {**(memo.evidence_json or {}), "reviewed_projection": views,
                          "review_input_fingerprint": fingerprint},
    }
    if all(getattr(memo, key) == value for key, value in values.items()):
        return
    for key, value in values.items():
        setattr(memo, key, value)
    memo.approved_by = None
    memo.approved_at = None
    await session.flush()
