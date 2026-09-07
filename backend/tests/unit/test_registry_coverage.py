import pytest
from sqlalchemy import select
from app.infrastructure.database.models import RiskFinding
from app.infrastructure.providers.base import RegistryRecord, RegistrySearchResults
from app.services.conflict_search import run_conflict_search
from tests.unit.test_conflict_semantic_layer import application


@pytest.mark.asyncio
async def test_truncated_nonempty_search_keeps_candidate_and_is_incomplete(async_session, application):
    application.mark_text = "ORBIT"
    records = [RegistryRecord(record_id=str(i), mark_text="ORBIT" if i == 8 else f"OTHER{i}",
        mark_type="word", owner="Test", classes=[25], status="registered",
        filing_date="2020-01-01", registration_date=None, goods_services="одежда") for i in range(9)]
    class Registry:
        async def search_marks(self, query):
            return RegistrySearchResults(records, total=100, truncated=True, source="registration")
    result = await run_conflict_search(async_session, application, registry_provider=Registry(), llm_provider=None)
    assert result.is_inconclusive
    assert result.verification_json["search_complete"] is False
    assert result.verification_json["query_coverage"][0]["total"] == 100
    assert result.verification_json["records_not_reviewed_by_llm"] == 9
    findings = (await async_session.scalars(select(RiskFinding).where(RiskFinding.assessment_id == result.id))).all()
    assert any("ORBIT" in finding.explanation for finding in findings)
