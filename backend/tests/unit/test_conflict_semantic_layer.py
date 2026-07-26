"""Смысловой слой внутри поиска конфликтов.

Проверяется главное следствие этапа: пара «ЯБЛОКО» / «APPLE» больше
не теряется. По звуку и начертанию она не проходит порог и раньше
отбрасывалась до того, как её кто-либо оценил по смыслу.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import (
    ApplicationStatus,
    Client,
    ClientType,
    ConflictSearchJob,
    MarkType,
    NiceClassSuggestion,
    RiskFinding,
    TrademarkApplicationDraft,
)
from app.infrastructure.llm.mock_provider import MockLLMProvider
from app.infrastructure.providers.base import RegistryRecord
from app.services.conflict_search import run_conflict_search
from sqlalchemy import select


class StubRegistry:
    """Реестр из одной записи: нужен предсказуемый противопоставленный знак."""

    def __init__(self, mark_text: str, classes: list[int]):
        self._record = RegistryRecord(
            record_id="RU9999001",
            mark_text=mark_text,
            mark_type="word",
            owner='ООО "Фрукты"',
            classes=classes,
            status="registered",
            filing_date=None,
            registration_date=None,
        )
        self.queries = 0

    async def search_marks(self, query):
        self.queries += 1
        return [self._record]


class RecordingRegistry(StubRegistry):
    """Реестр, запоминающий тексты запросов.

    ``only_for`` имитирует поведение настоящего реестра: запись
    возвращается лишь на запрос с подходящим написанием.
    """

    def __init__(self, mark_text: str, classes: list[int], only_for: str = ""):
        super().__init__(mark_text, classes)
        self.queried_texts: list[str] = []
        self._only_for = only_for.casefold()

    async def search_marks(self, query):
        self.queried_texts.append(query.mark_text)
        if self._only_for and query.mark_text.casefold() != self._only_for:
            return []
        return await super().search_marks(query)


@pytest.fixture
async def application(async_session) -> TrademarkApplicationDraft:
    client = Client(
        type=ClientType.company,
        full_name_or_company_name='ООО "Сад"',
    )
    async_session.add(client)
    await async_session.flush()

    draft = TrademarkApplicationDraft(
        client_id=client.id,
        mark_name="ЯБЛОКО",
        mark_text="ЯБЛОКО",
        mark_type=MarkType.word,
        status=ApplicationStatus.draft,
        goods_services_raw="одежда",
    )
    async_session.add(draft)
    await async_session.flush()
    return draft


async def _findings(session, assessment_id: int) -> list[RiskFinding]:
    return list(
        (
            await session.execute(
                select(RiskFinding).where(RiskFinding.assessment_id == assessment_id)
            )
        )
        .scalars()
        .all()
    )


class TestCrossLanguageConflict:
    async def test_pair_is_missed_without_the_model(self, async_session, application):
        """Без модели пара не проходит порог — так было до этапа."""
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [25]),
            llm_provider=None,
        )

        assert await _findings(async_session, assessment.id) == []
        assert assessment.llm_used is False
        assert any(
            "языковая модель недоступна" in limit.lower()
            for limit in assessment.limitations_json
        )

    async def test_pair_is_found_with_the_model(self, async_session, application):
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [25]),
            llm_provider=MockLLMProvider(),
        )

        findings = await _findings(async_session, assessment.id)
        assert len(findings) == 1
        assert "APPLE" in findings[0].explanation
        assert "прямой перевод" in findings[0].explanation

    async def test_model_usage_is_recorded(self, async_session, application):
        """Специалист должен видеть, что вывод опирается на модель."""
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [25]),
            llm_provider=MockLLMProvider(),
        )

        assert assessment.llm_used is True
        assert assessment.model_name == MockLLMProvider.MODEL_NAME
        assert assessment.verification_json["semantic_checks"] == 1
        assert any(
            "языковой моделью" in limit for limit in assessment.limitations_json
        )

        findings = await _findings(async_session, assessment.id)
        verdict = findings[0].verification_json["semantic_verdict"]
        assert verdict["relation"] == "translation"
        assert verdict["llm_used"] is True

    async def test_specialist_review_is_still_required(
        self, async_session, application
    ):
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [25]),
            llm_provider=MockLLMProvider(),
        )
        assert assessment.requires_specialist_review is True


class TestQueryIsExpanded:
    """Реестр ищет по написанию: знак-перевод надо сначала найти."""

    async def test_registry_is_queried_by_translation(
        self, async_session, application
    ):
        registry = RecordingRegistry("APPLE", [25])
        await run_conflict_search(
            async_session,
            application,
            registry_provider=registry,
            llm_provider=MockLLMProvider(),
        )

        assert "APPLE" in registry.queried_texts

    async def test_registry_is_queried_by_transliteration(
        self, async_session, application
    ):
        registry = RecordingRegistry("APPLE", [25])
        await run_conflict_search(
            async_session,
            application,
            registry_provider=registry,
            llm_provider=None,
        )

        # Транслитерация считается правилами и не требует модели.
        assert "YABLOKO" in registry.queried_texts

    async def test_variants_are_recorded_in_the_job(
        self, async_session, application
    ):
        """Специалист должен видеть, по чему именно искали."""
        await run_conflict_search(
            async_session,
            application,
            registry_provider=RecordingRegistry("APPLE", [25]),
            llm_provider=MockLLMProvider(),
        )

        job = (
            await async_session.execute(
                select(ConflictSearchJob).where(
                    ConflictSearchJob.application_id == application.id
                )
            )
        ).scalar_one()
        kinds = {v["kind"] for v in job.search_strategy_json["query_variants"]}
        assert kinds == {"original", "transliteration", "translation"}

    async def test_finding_shows_how_the_record_was_found(
        self, async_session, application
    ):
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=RecordingRegistry("APPLE", [25], only_for="APPLE"),
            llm_provider=MockLLMProvider(),
        )

        findings = await _findings(async_session, assessment.id)
        assert findings[0].verification_json["found_by"] == "translation"


class TestModelIsNotAskedNeedlessly:
    """Смысловая проверка идёт по парам и стоит вызова на каждую."""

    async def test_unrelated_marks_do_not_become_conflicts(
        self, async_session, application
    ):
        """Модель не должна превращать любое слово в конфликт."""
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("РАДУГА", [25]),
            llm_provider=MockLLMProvider(),
        )

        assert await _findings(async_session, assessment.id) == []

    async def test_different_classes_skip_the_model(self, async_session, application):
        """Товары неоднородны — смысловое совпадение вывод не изменит."""
        async_session.add(
            NiceClassSuggestion(
                application_id=application.id,
                class_number=25,
                approved=True,
            )
        )
        await async_session.flush()

        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [1]),
            llm_provider=MockLLMProvider(),
        )

        assert assessment.verification_json["semantic_checks"] == 0

    async def test_unknown_classes_still_trigger_the_check(
        self, async_session, application
    ):
        """Классы не заполнены — однородность не опровергнута, а неизвестна."""
        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [1]),
            llm_provider=MockLLMProvider(),
        )

        assert assessment.verification_json["semantic_checks"] == 1
        assert any(
            "Классы МКТУ не определены" in limit
            for limit in assessment.limitations_json
        )

    async def test_broken_model_does_not_break_the_search(
        self, async_session, application
    ):
        class BrokenLLM:
            MODEL_NAME = "broken"

            async def generate(self, *args, **kwargs):
                raise RuntimeError("сервис недоступен")

        assessment = await run_conflict_search(
            async_session,
            application,
            registry_provider=StubRegistry("APPLE", [25]),
            llm_provider=BrokenLLM(),
        )

        # Поиск завершился, оценка сохранена, модель не использована.
        assert assessment.id is not None
        assert assessment.llm_used is False
        assert assessment.verification_json["semantic_checks"] == 0
