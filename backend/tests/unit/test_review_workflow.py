import pytest
import io
from docx import Document
from sqlalchemy import select
from app.api.v1.endpoints.risk import review_finding, FindingReviewRequest, risk_report
from app.infrastructure.database.models import (
    AnalysisKind, AuditLog, NiceClassSuggestion, RecommendationMemo, RiskAssessment,
    RiskFinding, RiskLevel, User, UserRole,
)
from app.services.reviewed_risks import refresh_reviewed_memo
from app.services.filing_package import _latest_assessments, _analysis_document
from tests.unit.test_conflict_semantic_layer import application


@pytest.mark.asyncio
async def test_review_updates_report_memo_and_history_but_preserves_machine(async_session, application):
    user = User(email="review@test.local", hashed_password="unused", role=UserRole.admin)
    async_session.add(user)
    async_session.add(NiceClassSuggestion(application_id=application.id, class_number=25,
        class_description="одежда", approved=True))
    absolute = RiskAssessment(application_id=application.id, analysis_kind=AnalysisKind.absolute_grounds,
        overall_risk=RiskLevel.high, is_inconclusive=False, classes_confirmed=True, classes_considered_json=[25])
    relative = RiskAssessment(application_id=application.id, analysis_kind=AnalysisKind.relative_grounds,
        overall_risk=RiskLevel.low, is_inconclusive=False, classes_confirmed=True, classes_considered_json=[25])
    memo = RecommendationMemo(application_id=application.id, summary="Машинная оценка")
    async_session.add_all([absolute, relative, memo])
    await async_session.flush()
    finding = RiskFinding(assessment_id=absolute.id, category="descriptive", level=RiskLevel.high,
        explanation="Исходный машинный вывод о высоком риске")
    async_session.add(finding)
    await async_session.flush()
    await review_finding(finding.id, FindingReviewRequest(decision="reject", comment="Описательное значение не относится к этим товарам"), async_session, user)
    report = await risk_report(application.id, async_session, user)
    assert report["overall_risk"] == "low"
    assert report["sections"]["absolute_grounds"]["machine_overall_risk"] == "high"
    assert memo.key_risks_json == []
    assert "low" in memo.risk_assessment
    assert absolute.overall_risk == RiskLevel.high
    exported = await _latest_assessments(async_session, application.id)
    assert exported["absolute_grounds"].overall_risk is RiskLevel.low
    document = Document(io.BytesIO(_analysis_document(application, exported)))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Исходный машинный вывод о высоком риске" not in text
    assert "Учтены решения специалиста" in text
    memo.approved_by = user.id
    await async_session.flush()
    await refresh_reviewed_memo(async_session, application)
    assert memo.approved_by == user.id  # Чтение неизменённого отчёта не снимает утверждение.
    await review_finding(finding.id, FindingReviewRequest(decision="approve", comment="Пересмотр после обсуждения"), async_session, user)
    audits = (await async_session.scalars(select(AuditLog).where(AuditLog.entity_type == "RiskFinding").order_by(AuditLog.id))).all()
    assert len(audits) == 2
    assert audits[1].old_value_json["decision"] == "reject"
    application.goods_services_raw = "пищевые продукты"
    # Меняем именно выбранные товары, которые являются входом проверки.
    suggestion = await async_session.scalar(select(NiceClassSuggestion))
    suggestion.class_description = "пищевые продукты"
    await async_session.flush()
    await refresh_reviewed_memo(async_session, application)
    report = await risk_report(application.id, async_session, user)
    assert report["sections"]["absolute_grounds"]["review_stale"]
    assert not report["is_complete"]
    exported = await _latest_assessments(async_session, application.id)
    assert exported["absolute_grounds"].review_stale
    assert exported["absolute_grounds"].is_inconclusive
    from app.services.client_progress import client_progress
    progress = await client_progress(async_session, [application])
    assert progress[application.id]["client_progress_state"] == "incomplete"
