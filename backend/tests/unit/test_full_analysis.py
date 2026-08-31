"""Полный правовой анализ: порядок проверок и сводный вердикт.

Порядок не косметический: охраноспособность оценивается только
в отношении конкретных товаров, поэтому классы МКТУ определяются
до правовых проверок. Вердикт обязан учитывать оба блока оснований
и не должен выглядеть благополучным, если часть проверок не прошла.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    AnalysisKind,
    ApplicationStatus,
    Client,
    ClientType,
    MarkType,
    NiceClassSuggestion,
    RiskAssessment,
    RiskLevel,
    TrademarkApplicationDraft,
)
from app.infrastructure.llm.mock_provider import MockLLMProvider
from app.infrastructure.providers.base import RegistryRecord
from app.services.full_analysis import _max_risk, run_full_analysis


class StubRegistry:
    def __init__(self, records: list[RegistryRecord] | None = None):
        self._records = records or []

    async def search_marks(self, query):
        return list(self._records)


@pytest.fixture
async def application(async_session) -> TrademarkApplicationDraft:
    client = Client(
        type=ClientType.company, full_name_or_company_name='ООО "Сад"'
    )
    async_session.add(client)
    await async_session.flush()

    draft = TrademarkApplicationDraft(
        client_id=client.id,
        mark_name="ЯБЛОКО",
        mark_text="ЯБЛОКО",
        mark_type=MarkType.word,
        status=ApplicationStatus.draft,
        business_description="производство одежды",
        goods_services_raw="одежда, обувь",
    )
    async_session.add(draft)
    await async_session.flush()
    return draft


async def _run(session, application, registry=None):
    return await run_full_analysis(
        session,
        application,
        llm_provider=MockLLMProvider(),
        registry_provider=registry or StubRegistry(),
    )


class TestOrder:
    async def test_all_three_steps_are_executed(self, async_session, application):
        result = await _run(async_session, application)
        steps = [s["step"] for s in result["steps"]]
        assert steps == ["classes", "absolute_grounds", "relative_grounds"]

    async def test_classes_come_before_legal_checks(
        self, async_session, application
    ):
        """Классы определяются первыми — от них зависит оценка."""
        result = await _run(async_session, application)
        assert result["steps"][0]["step"] == "classes"

    async def test_existing_classes_are_not_overwritten(
        self, async_session, application
    ):
        """Подтверждённый специалистом перечень заново не подбирается."""
        async_session.add(
            NiceClassSuggestion(
                application_id=application.id, class_number=25, approved=True
            )
        )
        await async_session.flush()

        result = await _run(async_session, application)
        classes_step = result["steps"][0]
        assert classes_step["status"] == "skipped"
        assert result["classes_considered"] == [25]

    async def test_progress_reports_real_analysis_phases(
        self, async_session, application
    ):
        events: list[tuple[str, int, str]] = []

        async def report(step: str, percent: int, detail: str) -> None:
            events.append((step, percent, detail))

        await run_full_analysis(
            async_session,
            application,
            llm_provider=MockLLMProvider(),
            registry_provider=StubRegistry(),
            progress_callback=report,
        )

        assert [event[0] for event in events] == [
            "classes",
            "absolute_grounds",
            "relative_grounds",
            "recommendation",
            "completed",
        ]
        assert events[-1][1] == 100

    async def test_retry_reuses_completed_analysis_sections(
        self, async_session, application
    ):
        from sqlalchemy import func, select

        await _run(async_session, application)
        assessments = list(
            (
                await async_session.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.application_id == application.id
                    )
                )
            )
            .scalars()
            .all()
        )
        # The mock intentionally returns cautious/inconclusive answers.  Mark
        # both persisted sections as completed to exercise the retry contract.
        for assessment in assessments:
            assessment.is_inconclusive = False
            assessment.inconclusive_reason = None
            assessment.overall_risk = assessment.overall_risk or RiskLevel.low
            # A pipeline skip is not a completed registry result.  This test
            # converts both rows into completed sections deliberately.
            assessment.verification_json = {}
        await async_session.flush()
        before = (
            await async_session.execute(
                select(func.count(RiskAssessment.id)).where(
                    RiskAssessment.application_id == application.id
                )
            )
        ).scalar_one()

        result = await run_full_analysis(
            async_session,
            application,
            llm_provider=MockLLMProvider(),
            registry_provider=StubRegistry(),
            retry_incomplete_only=True,
        )
        after = (
            await async_session.execute(
                select(func.count(RiskAssessment.id)).where(
                    RiskAssessment.application_id == application.id
                )
            )
        ).scalar_one()

        assert after == before
        assert [step["status"] for step in result["steps"][1:]] == [
            "reused",
            "reused",
        ]

    async def test_failed_refresh_keeps_completed_result_for_same_classes(
        self, async_session, application, monkeypatch
    ):
        """Сбой обновления не уничтожает готовую проверку той же области охраны."""
        import app.services.full_analysis as full_analysis_module

        async_session.add(
            NiceClassSuggestion(
                application_id=application.id, class_number=25, approved=True
            )
        )
        await async_session.flush()

        for kind in (AnalysisKind.absolute_grounds, AnalysisKind.relative_grounds):
            async_session.add(
                RiskAssessment(
                    application_id=application.id,
                    analysis_kind=kind,
                    overall_risk=RiskLevel.low,
                    summary="Проверка завершена.",
                    is_inconclusive=False,
                    classes_considered_json=[25],
                    classes_confirmed=True,
                )
            )
        # Последняя попытка поиска не завершилась, поэтому retry должен её
        # повторить, но при повторном сбое сохранить предыдущий готовый вывод.
        async_session.add(
            RiskAssessment(
                application_id=application.id,
                analysis_kind=AnalysisKind.relative_grounds,
                is_inconclusive=True,
                inconclusive_reason="Реестр временно не ответил.",
                classes_considered_json=[25],
                classes_confirmed=True,
            )
        )
        await async_session.flush()

        async def failed_registry_refresh(*args, **kwargs):
            attempt = RiskAssessment(
                application_id=application.id,
                analysis_kind=AnalysisKind.relative_grounds,
                is_inconclusive=True,
                inconclusive_reason="Не удалось обновить реестр.",
                classes_considered_json=[25],
                classes_confirmed=True,
            )
            async_session.add(attempt)
            await async_session.flush()
            return attempt

        monkeypatch.setattr(
            full_analysis_module, "run_conflict_search", failed_registry_refresh
        )

        result = await run_full_analysis(
            async_session,
            application,
            llm_provider=MockLLMProvider(),
            registry_provider=StubRegistry(),
            retry_incomplete_only=True,
        )

        relative_step = next(
            step for step in result["steps"] if step["step"] == "relative_grounds"
        )
        assert relative_step["status"] == "reused_after_refresh_failure"
        assert result["is_complete"] is True
        assert result["overall_risk"] == "low"
        assert result["refresh_warnings"] == [
            {
                "step": "relative_grounds",
                "detail": "Не удалось обновить реестр.",
            }
        ]

    async def test_completed_absolute_result_is_not_reused_after_facts_change(
        self, async_session, application
    ):
        """Одинаковый класс не делает старый вывод пригодным для нового товара."""
        from app.services.full_analysis import latest_completed_for_classes

        assessment = RiskAssessment(
            application_id=application.id,
            analysis_kind=AnalysisKind.absolute_grounds,
            overall_risk=RiskLevel.low,
            summary="Проверка завершена.",
            is_inconclusive=False,
            classes_considered_json=[25],
            classes_confirmed=True,
            verification_json={"input_fingerprint": "old-facts"},
        )
        async_session.add(assessment)
        await async_session.flush()

        stale = await latest_completed_for_classes(
            async_session,
            application.id,
            AnalysisKind.absolute_grounds,
            classes=[25],
            classes_confirmed=True,
            input_fingerprint="new-facts",
        )
        current = await latest_completed_for_classes(
            async_session,
            application.id,
            AnalysisKind.absolute_grounds,
            classes=[25],
            classes_confirmed=True,
            input_fingerprint="old-facts",
        )

        assert stale is None
        assert current is assessment

    async def test_high_absolute_risk_stops_registry_search(
        self, async_session, application, monkeypatch
    ):
        """An independent refusal ground must stop the expensive next phase."""
        import app.services.full_analysis as full_analysis_module

        async_session.add(
            NiceClassSuggestion(
                application_id=application.id, class_number=25, approved=True
            )
        )
        await async_session.flush()

        async def high_absolute(*args, **kwargs):
            assessment = RiskAssessment(
                application_id=application.id,
                analysis_kind=AnalysisKind.absolute_grounds,
                overall_risk=RiskLevel.high,
                summary="Обозначение содержит самостоятельное основание для отказа.",
                is_inconclusive=False,
                classes_considered_json=[25],
                classes_confirmed=True,
            )
            async_session.add(assessment)
            await async_session.flush()
            return assessment

        registry_called = False

        async def registry_search(*args, **kwargs):
            nonlocal registry_called
            registry_called = True
            raise AssertionError("Registry search must not run after a high absolute risk")

        monkeypatch.setattr(
            full_analysis_module, "run_absolute_grounds_analysis", high_absolute
        )
        monkeypatch.setattr(full_analysis_module, "run_conflict_search", registry_search)

        result = await run_full_analysis(
            async_session,
            application,
            llm_provider=MockLLMProvider(),
            registry_provider=StubRegistry(),
        )

        assert registry_called is False
        assert result["overall_risk"] == "high"
        assert result["is_complete"] is True
        relative_step = next(
            step for step in result["steps"] if step["step"] == "relative_grounds"
        )
        assert relative_step["status"] == "not_required"

        relative = (
            await async_session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.application_id == application.id,
                    RiskAssessment.analysis_kind == AnalysisKind.relative_grounds,
                )
                .order_by(RiskAssessment.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert relative.search_mode.value == "not_performed"
        assert relative.verification_json["skipped"] is True
        assert relative.verification_json["blocked_by"] == "absolute_grounds"

    async def test_low_absolute_risk_allows_registry_search(
        self, async_session, application, monkeypatch
    ):
        import app.services.full_analysis as full_analysis_module

        async_session.add(
            NiceClassSuggestion(
                application_id=application.id, class_number=25, approved=True
            )
        )
        await async_session.flush()

        async def low_absolute(*args, **kwargs):
            assessment = RiskAssessment(
                application_id=application.id,
                analysis_kind=AnalysisKind.absolute_grounds,
                overall_risk=RiskLevel.low,
                summary="Самостоятельных препятствий не выявлено.",
                is_inconclusive=False,
                classes_considered_json=[25],
                classes_confirmed=True,
            )
            async_session.add(assessment)
            await async_session.flush()
            return assessment

        registry_called = False

        async def registry_search(*args, **kwargs):
            nonlocal registry_called
            registry_called = True
            assessment = RiskAssessment(
                application_id=application.id,
                analysis_kind=AnalysisKind.relative_grounds,
                overall_risk=RiskLevel.low,
                summary="Поиск по реестру завершён.",
                is_inconclusive=False,
                classes_considered_json=[25],
                classes_confirmed=True,
            )
            async_session.add(assessment)
            await async_session.flush()
            return assessment

        monkeypatch.setattr(
            full_analysis_module, "run_absolute_grounds_analysis", low_absolute
        )
        monkeypatch.setattr(full_analysis_module, "run_conflict_search", registry_search)

        result = await run_full_analysis(
            async_session,
            application,
            llm_provider=MockLLMProvider(),
            registry_provider=StubRegistry(),
        )

        assert registry_called is True
        relative_step = next(
            step for step in result["steps"] if step["step"] == "relative_grounds"
        )
        assert relative_step["status"] == "ok"


class TestVerdict:
    async def test_verdict_is_always_produced(self, async_session, application):
        result = await _run(async_session, application)
        assert result["verdict"]
        assert result["verdict_text"]

    async def test_specialist_review_is_required(self, async_session, application):
        result = await _run(async_session, application)
        assert result["requires_specialist_review"] is True
        assert "проверки специалистом" in result["disclaimer"]

    async def test_verdict_takes_the_highest_risk(self):
        """Итог определяется наиболее серьёзным основанием."""
        assert _max_risk([RiskLevel.low, RiskLevel.critical]) is RiskLevel.critical
        assert _max_risk([RiskLevel.medium, RiskLevel.high]) is RiskLevel.high
        assert _max_risk([]) is None

    async def test_both_grounds_are_assessed(self, async_session, application):
        """В деле должны появиться оценки по обоим видам оснований."""
        await _run(async_session, application)

        from sqlalchemy import select

        kinds = set(
            (
                await async_session.execute(
                    select(RiskAssessment.analysis_kind).where(
                        RiskAssessment.application_id == application.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert AnalysisKind.absolute_grounds in kinds
        assert AnalysisKind.relative_grounds in kinds


class TestIncompleteChecks:
    async def test_limitations_are_carried_into_the_verdict(
        self, async_session, application
    ):
        """Ограничения поиска обязаны дойти до итогового экрана."""
        result = await _run(async_session, application)
        assert result["limitations"]

    async def test_incomplete_analysis_is_flagged(self, async_session, application):
        """Дело без обозначения нельзя признать проверенным."""
        application.mark_text = None
        application.mark_name = None
        await async_session.flush()

        result = await _run(async_session, application)
        assert result["is_complete"] is False
        assert result["incomplete_checks"]


class TestMemo:
    """Итог анализа должен оставаться в деле, а не только на экране."""

    async def _memo(self, session, application_id):
        from sqlalchemy import select

        from app.infrastructure.database.models import RecommendationMemo

        return (
            await session.execute(
                select(RecommendationMemo).where(
                    RecommendationMemo.application_id == application_id
                )
            )
        ).scalar_one_or_none()

    async def test_memo_is_created(self, async_session, application):
        await _run(async_session, application)
        memo = await self._memo(async_session, application.id)

        assert memo is not None
        assert memo.summary
        assert memo.recommended_action is not None

    async def test_memo_is_not_approved_automatically(
        self, async_session, application
    ):
        """Вывод остаётся предварительным до решения специалиста."""
        await _run(async_session, application)
        memo = await self._memo(async_session, application.id)
        assert memo.approved_by is None

    async def test_rerun_updates_the_same_memo(self, async_session, application):
        from sqlalchemy import func, select

        from app.infrastructure.database.models import RecommendationMemo

        await _run(async_session, application)
        await _run(async_session, application)

        count = (
            await async_session.execute(
                select(func.count(RecommendationMemo.id)).where(
                    RecommendationMemo.application_id == application.id
                )
            )
        ).scalar_one()
        assert count == 1

    async def test_incomplete_analysis_lowers_confidence(
        self, async_session, application
    ):
        """Неполная проверка не может быть уверенной."""
        application.mark_text = None
        application.mark_name = None
        await async_session.flush()

        await _run(async_session, application)
        memo = await self._memo(async_session, application.id)
        assert memo.confidence is None
