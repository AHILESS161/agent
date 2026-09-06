from types import SimpleNamespace as NS
from app.infrastructure.database.models import RiskLevel, ReviewerDecision
from app.services.reviewed_risks import reviewed_view


def finding(id, level, decision=None, fingerprint="v1"):
    return NS(id=id, level=RiskLevel(level), reviewer_decision=decision,
              verification_json={"review_input_fingerprint": fingerprint})


def test_rejected_high_risk_does_not_hide_independent_medium_risk():
    assessment = NS(overall_risk=RiskLevel.high, is_inconclusive=False)
    result = reviewed_view(assessment, [finding(1, "high", ReviewerDecision.reject), finding(2, "medium")], "v1")
    assert result["overall_risk"] == "medium"
    assert result["machine_overall_risk"] == "high"
    assert result["active_finding_ids"] == [2]
    assert assessment.overall_risk == RiskLevel.high


def test_new_facts_invalidate_previous_rejection():
    assessment = NS(overall_risk=RiskLevel.high, is_inconclusive=False)
    result = reviewed_view(assessment, [finding(1, "high", ReviewerDecision.reject)], "v2")
    assert result["overall_risk"] == "high"
    assert result["review_stale"] and result["is_inconclusive"]


def test_revision_request_and_incomplete_checks_never_become_clearance():
    assessment = NS(overall_risk=RiskLevel.low, is_inconclusive=False)
    result = reviewed_view(assessment, [finding(1, "low", ReviewerDecision.modify)], "v1")
    assert result["overall_risk"] is None
    assert result["is_inconclusive"]
