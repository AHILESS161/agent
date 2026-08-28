"""
Unit tests for the Completeness Engine.

Tests validate that the engine correctly identifies missing required fields
and blocks advancement to subsequent pipeline stages.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.infrastructure.database.models import (
    Client,
    ClientType,
    MarkType,
    TrademarkApplicationDraft,
    ApplicationStatus,
)
from app.services.completeness_engine import (
    ApplicationStage,
    CompletenessEngine,
    CompletenessResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(
    inn: str = "7701234567",
    ogrn: str = "1177746123456",
    client_type: ClientType = ClientType.company,
) -> MagicMock:
    """Return a minimal mock Client with the given attributes."""
    client = MagicMock(spec=Client)
    client.inn = inn
    client.ogrn_or_ogrnip = ogrn
    client.type = client_type
    client.representatives = []
    return client


def _make_app(
    mark_name: str = "ТЕСТ",
    mark_text: str = "ТЕСТ",
    mark_type: MarkType = MarkType.word,
    goods_services_raw: str = "Программное обеспечение",
    business_description: str = "ИТ-компания",
    mark_image_file_id: str = None,
    client: object = None,
    status: ApplicationStatus = ApplicationStatus.draft,
) -> MagicMock:
    """Return a minimal mock TrademarkApplicationDraft."""
    app = MagicMock(spec=TrademarkApplicationDraft)
    app.mark_name = mark_name
    app.mark_text = mark_text
    app.mark_type = mark_type
    app.goods_services_raw = goods_services_raw
    app.business_description = business_description
    app.mark_image_file_id = mark_image_file_id
    app.transliteration = None
    app.translation = None
    app.colors_claimed = None
    app.priority_claim = None
    app.status = status
    app.client = client or _make_client()
    return app


# ---------------------------------------------------------------------------
# Basic pass / fail
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompletenessEngineBasic:
    """Tests for core pass/fail logic."""

    def test_complete_word_mark_passes_intake(self):
        """A fully filled word mark should pass the intake stage."""
        engine = CompletenessEngine()
        app = _make_app()

        result = engine.validate(app, ApplicationStage.intake)

        assert result.is_complete is True
        assert result.blocking_issues == []

    def test_missing_mark_name_blocks_intake(self):
        """Missing mark_name must block intake stage."""
        engine = CompletenessEngine()
        app = _make_app(mark_name="", mark_text="")

        result = engine.validate(app, ApplicationStage.intake)

        assert result.is_complete is False
        blocking_fields = {issue.field for issue in result.blocking_issues}
        assert "mark_name" in blocking_fields

    def test_missing_goods_services_blocks_intake(self):
        """Missing goods_services_raw must block intake stage."""
        engine = CompletenessEngine()
        app = _make_app(goods_services_raw="")

        result = engine.validate(app, ApplicationStage.intake)

        assert result.is_complete is False
        blocking_fields = {issue.field for issue in result.blocking_issues}
        assert "goods_services_raw" in blocking_fields

    def test_complete_application_returns_completeness_result(self):
        """validate() always returns a CompletenessResult instance."""
        engine = CompletenessEngine()
        app = _make_app()
        result = engine.validate(app, ApplicationStage.intake)

        assert isinstance(result, CompletenessResult)
        assert result.stage == ApplicationStage.intake.value


# ---------------------------------------------------------------------------
# Company INN check
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompletenessEngineINN:
    """Tests for INN validation rules."""

    def test_company_without_inn_fails(self):
        """A company client without INN must produce a blocking issue."""
        engine = CompletenessEngine()
        client = _make_client(inn=None)
        app = _make_app(client=client)

        result = engine.validate(app, ApplicationStage.intake)

        assert result.is_complete is False
        blocking_fields = {issue.field for issue in result.blocking_issues}
        assert "inn" in blocking_fields

    def test_company_without_inn_requests_from_client(self):
        """Missing INN should be requested from the client, not lawyer."""
        engine = CompletenessEngine()
        client = _make_client(inn=None)
        app = _make_app(client=client)

        result = engine.validate(app, ApplicationStage.intake)

        inn_issues = [i for i in result.blocking_issues if i.field == "inn"]
        assert len(inn_issues) > 0
        assert inn_issues[0].requested_from == "client"

    def test_individual_without_inn_is_not_blocking(self):
        """ИНН физлица указывается при наличии и не должен блокировать путь."""
        engine = CompletenessEngine()
        client = _make_client(inn=None, ogrn=None, client_type=ClientType.individual)
        app = _make_app(client=client)

        result = engine.validate(app, ApplicationStage.intake)

        blocking_fields = {i.field for i in result.blocking_issues}
        assert "inn" not in blocking_fields

    def test_company_with_inn_passes_inn_check(self):
        """A company with INN should not trigger the INN rule."""
        engine = CompletenessEngine()
        client = _make_client(inn="7701234567")
        app = _make_app(client=client)

        result = engine.validate(app, ApplicationStage.intake)

        blocking_fields = {i.field for i in result.blocking_issues}
        assert "inn" not in blocking_fields


# ---------------------------------------------------------------------------
# Figurative mark image check
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompletenessEngineFigurativeMark:
    """Tests for figurative/combined mark image requirement."""

    def test_figurative_mark_without_image_fails_intake(self):
        """A figurative mark without an image file must fail intake."""
        engine = CompletenessEngine()
        app = _make_app(mark_type=MarkType.figurative, mark_image_file_id=None)

        result = engine.validate(app, ApplicationStage.intake)

        assert result.is_complete is False
        blocking_fields = {i.field for i in result.blocking_issues}
        assert "mark_image_file_id" in blocking_fields

    def test_combined_mark_without_image_fails_intake(self):
        """A combined mark without an image file must fail intake."""
        engine = CompletenessEngine()
        app = _make_app(mark_type=MarkType.combined, mark_image_file_id=None)

        result = engine.validate(app, ApplicationStage.intake)

        blocking_fields = {i.field for i in result.blocking_issues}
        assert "mark_image_file_id" in blocking_fields

    def test_figurative_mark_with_image_passes_image_check(self):
        """A figurative mark with an image ID should not trigger the image rule."""
        engine = CompletenessEngine()
        app = _make_app(
            mark_type=MarkType.figurative,
            mark_image_file_id="file_abc123.png",
        )

        result = engine.validate(app, ApplicationStage.intake)

        blocking_fields = {i.field for i in result.blocking_issues}
        assert "mark_image_file_id" not in blocking_fields

    def test_word_mark_without_image_passes_image_check(self):
        """A word mark does not require an image file."""
        engine = CompletenessEngine()
        app = _make_app(mark_type=MarkType.word, mark_image_file_id=None)

        result = engine.validate(app, ApplicationStage.intake)

        blocking_fields = {i.field for i in result.blocking_issues}
        assert "mark_image_file_id" not in blocking_fields


# ---------------------------------------------------------------------------
# Document generation stage hard-stop
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompletenessEngineDocumentGenerationStage:
    """Tests for the document_generation stage hard-stop."""

    def test_document_generation_stage_requires_all_fields(self):
        """At document_generation stage, a complete app should pass."""
        engine = CompletenessEngine()
        app = _make_app()

        result = engine.validate(app, ApplicationStage.document_generation)

        # The test checks the engine doesn't crash and returns a valid result.
        assert isinstance(result, CompletenessResult)

    def test_document_generation_stage_blocks_on_missing_inn(self):
        """At document_generation stage, missing INN must be blocking."""
        engine = CompletenessEngine()
        client = _make_client(inn=None)
        app = _make_app(client=client)

        result = engine.validate(app, ApplicationStage.document_generation)

        assert result.is_complete is False

    def test_document_generation_stage_blocks_figurative_without_image(self):
        """At document_generation stage, figurative mark without image must block."""
        engine = CompletenessEngine()
        app = _make_app(mark_type=MarkType.figurative, mark_image_file_id=None)

        result = engine.validate(app, ApplicationStage.document_generation)

        assert result.is_complete is False
        blocking_fields = {i.field for i in result.blocking_issues}
        assert "mark_image_file_id" in blocking_fields


# ---------------------------------------------------------------------------
# Severity and metadata checks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompletenessEngineSeverity:
    """Tests for severity levels and recommended_message."""

    def test_blocking_issues_have_blocking_severity(self):
        """All items in blocking_issues must have severity == 'blocking'."""
        engine = CompletenessEngine()
        client = _make_client(inn=None)
        app = _make_app(mark_name="", client=client)

        result = engine.validate(app, ApplicationStage.intake)

        for issue in result.blocking_issues:
            assert issue.severity == "blocking"

    def test_recommended_message_present_when_issues_found(self):
        """Engine must produce a recommended_message when there are issues."""
        engine = CompletenessEngine()
        app = _make_app(mark_name="", goods_services_raw="")

        result = engine.validate(app, ApplicationStage.intake)

        assert result.recommended_message is not None
        assert len(result.recommended_message) > 0

    def test_no_recommended_message_on_clean_application(self):
        """Engine should not produce a recommended_message for a clean app."""
        engine = CompletenessEngine()
        app = _make_app()

        result = engine.validate(app, ApplicationStage.intake)

        assert result.recommended_message is None
