"""Тесты сопоставления: выписка -> карточка дела -> заявление.

Маппинг определяет, какие данные попадут в юридически значимый документ,
поэтому конфигурация покрыта тестами наравне с кодом.
"""

from __future__ import annotations

import pytest

from app.document_processing.extractors import extract_registry_fields
from app.document_processing.mappers import FieldMappingEngine, build_reconciliation
from app.document_processing.mappers.field_mapping import (
    ACTION_ACCEPT,
    ACTION_EDIT,
    ACTION_LEAVE_EMPTY,
    ACTION_REJECT,
)
from app.infrastructure.database.models import FieldStatus
from tests.fixtures.egrul_sample import EGRUL_PAGES, EXPECTED


@pytest.fixture(scope="module")
def extracted():
    return extract_registry_fields(EGRUL_PAGES)


# Выписка ЕГРЮЛ — заявитель-юрлицо. Сверка теперь типозависима:
# у юрлица и ИП разные реестровые поля, поэтому тип передаётся всегда.
COMPANY = "company"


@pytest.fixture(scope="module")
def rows(extracted):
    result, _ = build_reconciliation(extracted, client_type=COMPANY)
    return {r.case_field: r for r in result}


class TestMappingConfiguration:
    def test_config_is_versioned(self):
        engine = FieldMappingEngine()
        assert engine.version >= 1
        assert engine.config["application_schema_version"]

    def test_declares_target_document_kind(self):
        engine = FieldMappingEngine()
        kinds = engine.config["applies_to_document_kind"]
        assert "egrul_extract" in kinds
        assert "egrip_extract" in kinds

    def test_unmapped_application_fields_are_declared_explicitly(self):
        """Отсутствие источника должно быть видимым, а не выглядеть
        как забытый маппинг."""
        engine = FieldMappingEngine()
        not_sourced = engine.config["not_sourced_from_registry"]
        assert not_sourced
        for entry in not_sourced:
            assert entry["field"]
            assert entry["reason"]

    def test_mark_kind_is_not_sourced_from_registry(self):
        """Вид знака отмечается чекбоксом и из выписки взяться не может."""
        engine = FieldMappingEngine()
        fields = {e["field"] for e in engine.config["not_sourced_from_registry"]}
        assert "application.mark.kind" in fields


class TestMappingChain:
    """Проверка цепочки реестр -> дело -> заявление."""

    @pytest.mark.parametrize(
        ("case_field", "registry_field", "application_field"),
        [
            ("case.applicant.full_name", "registry.legal_entity.full_name", "application.applicant.name"),
            ("case.applicant.inn", "registry.legal_entity.inn", "application.applicant.inn"),
            ("case.applicant.ogrn", "registry.legal_entity.ogrn", "application.applicant.ogrn"),
            ("case.applicant.legal_address", "registry.legal_entity.address.full", "application.applicant.address"),
        ],
    )
    def test_chain_is_wired(self, rows, case_field, registry_field, application_field):
        row = rows[case_field]
        assert row.registry_field == registry_field
        assert row.application_field == application_field

    def test_values_reach_the_mapping(self, rows):
        assert rows["case.applicant.ogrn"].registry_value == EXPECTED["ogrn"]
        assert rows["case.applicant.inn"].registry_value == EXPECTED["inn"]
        assert rows["case.applicant.full_name"].registry_value == EXPECTED["full_name"]

    def test_fields_without_application_target_are_kept_in_case(self, rows):
        """Сокращённое наименование в бланке не предусмотрено."""
        row = rows["case.applicant.short_name"]
        assert row.application_field is None
        assert row.registry_value == EXPECTED["short_name"]
        assert row.note


class TestTraceability:
    def test_each_row_reports_source_page(self, rows):
        for row in rows.values():
            if row.registry_value and row.registry_field:
                assert row.page_number is not None, row.label

    def test_each_row_reports_pattern_and_method(self, rows):
        for row in rows.values():
            if row.registry_value and row.registry_field:
                assert row.pattern_id, row.label
                assert row.extraction_method, row.label

    def test_normalisation_is_visible(self, rows):
        """Специалист должен видеть и исходное, и приведённое значение."""
        row = rows["case.applicant.full_name"]
        assert row.normalization_changed is True
        assert row.registry_raw_value != row.registry_value


class TestSpecialistActions:
    def test_found_value_offers_accept_edit_reject(self, rows):
        actions = rows["case.applicant.ogrn"].available_actions
        assert ACTION_ACCEPT in actions
        assert ACTION_EDIT in actions
        assert ACTION_REJECT in actions

    def test_required_field_cannot_be_left_empty(self, rows):
        """Обязательное поле нельзя просто оставить пустым."""
        assert ACTION_LEAVE_EMPTY not in rows["case.applicant.ogrn"].available_actions

    def test_optional_field_can_be_left_empty(self, rows):
        assert ACTION_LEAVE_EMPTY in rows["case.applicant.kpp"].available_actions

    def test_missing_value_cannot_be_accepted(self):
        """Принимать нечего, если значение не найдено."""
        result, _ = build_reconciliation(
            extract_registry_fields([(1, "пусто")]), client_type=COMPANY
        )
        rows = {r.case_field: r for r in result}
        actions = rows["case.applicant.full_name"].available_actions
        assert ACTION_ACCEPT not in actions
        assert ACTION_EDIT in actions


class TestConflictBetweenRegistryAndCase:
    def test_differing_case_value_produces_conflict(self, extracted):
        """Значение в карточке дела расходится с выпиской."""
        result, _ = build_reconciliation(
            extracted,
            case_values={"case.applicant.inn": "9999999999"},
            client_type=COMPANY,
        )
        rows = {r.case_field: r for r in result}
        row = rows["case.applicant.inn"]

        assert row.status is FieldStatus.conflict
        assert row.registry_value == EXPECTED["inn"]
        assert row.case_value == "9999999999"
        assert "отличается" in row.validation_error

    def test_identical_case_value_is_not_a_conflict(self, extracted):
        result, _ = build_reconciliation(
            extracted,
            case_values={"case.applicant.inn": EXPECTED["inn"]},
            client_type=COMPANY,
        )
        rows = {r.case_field: r for r in result}
        assert rows["case.applicant.inn"].status is not FieldStatus.conflict

    def test_case_only_address_is_already_confirmed(self):
        """Сохранённый пользователем адрес ИП не нужно требовать повторно."""
        result, _ = build_reconciliation(
            [],
            case_values={"case.applicant.legal_address": "г. Москва, ул. Пушкина, д. 23"},
            client_type="sole_proprietor",
        )
        row = next(r for r in result if r.case_field == "case.applicant.legal_address")

        assert row.status is FieldStatus.confirmed
        assert row.case_value == "г. Москва, ул. Пушкина, д. 23"
        assert row.blocks_document_generation is False

    def test_saved_country_code_overrides_default_suggestion(self):
        result, _ = build_reconciliation(
            [],
            case_values={"case.applicant.country_code": "RU"},
            client_type="sole_proprietor",
        )
        row = next(r for r in result if r.case_field == "case.applicant.country_code")

        assert row.case_value == "RU"
        assert row.status is FieldStatus.confirmed


class TestHumanInTheLoop:
    def test_composed_address_always_needs_review(self, rows):
        """Адрес собран из частей — подтверждение обязательно даже при
        успешном извлечении всех компонентов."""
        row = rows["case.applicant.legal_address"]
        assert row.status is FieldStatus.needs_review
        assert row.validation_error

    def test_default_value_is_a_suggestion_not_a_fact(self, rows):
        """Код страны RU предлагается, но не считается извлечённым."""
        row = rows["case.applicant.country_code"]
        assert row.default_value == "RU"
        assert row.registry_field is None
        assert row.status is FieldStatus.needs_review

    def test_unconfirmed_required_field_blocks_draft_generation(self, extracted):
        _, summary = build_reconciliation(extracted, client_type=COMPANY)
        assert summary["can_generate_draft"] is False
        assert summary["blocking_document_generation"]

    def test_no_row_is_auto_confirmed(self, rows):
        for row in rows.values():
            assert row.status is not FieldStatus.confirmed


class TestSpecialistDecisionIsFinal:
    """Решение специалиста не должно пересчитываться автоматикой.

    Регрессия: подтверждённое поле снова помечалось как конфликт,
    потому что значение в карточке дела по-прежнему отличалось
    от значения в выписке, — и работа человека терялась.
    """

    def _confirmed_field(self, field_id: str, value: str):
        from app.document_processing.extractors.registry import ExtractedFieldResult

        return ExtractedFieldResult(
            field_id=field_id,
            label="Тестовое поле",
            status=FieldStatus.confirmed,
            value=value,
            normalized_value=value,
            confidence=0.95,
            page_number=1,
        )

    def test_confirmed_field_stays_confirmed_despite_case_mismatch(self):
        confirmed = self._confirmed_field("registry.legal_entity.inn", "7707083893")
        result, _ = build_reconciliation(
            [confirmed],
            case_values={"case.applicant.inn": "9999999999"},
            client_type=COMPANY,
        )
        row = {r.case_field: r for r in result}["case.applicant.inn"]
        assert row.status is FieldStatus.confirmed

    def test_confirmed_composed_address_is_not_reset_to_needs_review(self):
        confirmed = self._confirmed_field(
            "registry.legal_entity.address.full", "101000, Москва"
        )
        result, _ = build_reconciliation([confirmed], client_type=COMPANY)
        row = {r.case_field: r for r in result}["case.applicant.legal_address"]
        assert row.status is FieldStatus.confirmed

    def test_confirmed_required_field_no_longer_blocks_draft(self):
        confirmed = self._confirmed_field(
            "registry.legal_entity.address.full", "101000, Москва"
        )
        result, _ = build_reconciliation([confirmed], client_type=COMPANY)
        row = {r.case_field: r for r in result}["case.applicant.legal_address"]
        assert row.blocks_document_generation is False

    def test_rejected_field_is_not_recomputed(self):
        from app.document_processing.extractors.registry import ExtractedFieldResult

        rejected = ExtractedFieldResult(
            field_id="registry.legal_entity.inn",
            label="ИНН",
            status=FieldStatus.rejected,
            value="7707083893",
            normalized_value="7707083893",
        )
        result, _ = build_reconciliation(
            [rejected],
            case_values={"case.applicant.inn": "9999999999"},
            client_type=COMPANY,
        )
        row = {r.case_field: r for r in result}["case.applicant.inn"]
        assert row.status is FieldStatus.rejected


class TestSummary:
    def test_summary_reports_versions(self, extracted):
        _, summary = build_reconciliation(extracted, client_type=COMPANY)
        assert summary["mapping_version"] >= 1
        assert summary["application_schema_version"]

    def test_summary_counts_match_rows(self, extracted):
        result, summary = build_reconciliation(extracted, client_type=COMPANY)
        assert summary["total"] == len(result)
        assert sum(summary["by_status"].values()) == len(result)

    def test_summary_lists_blocking_fields_by_label(self, extracted):
        _, summary = build_reconciliation(extracted, client_type=COMPANY)
        for label in summary["blocking_document_generation"]:
            assert isinstance(label, str) and label


class TestPrivacy:
    def test_director_rows_are_marked_sensitive(self, rows):
        for suffix in ("last_name", "first_name", "middle_name"):
            assert rows[f"case.applicant.director.{suffix}"].is_sensitive is True

    def test_company_identifiers_are_not_sensitive(self, rows):
        for suffix in ("inn", "ogrn", "kpp"):
            assert rows[f"case.applicant.{suffix}"].is_sensitive is False


class TestApplicationFieldLabels:
    """Технический путь поля специалисту ничего не говорит."""

    def test_mapped_rows_carry_human_label(self, rows):
        row = rows["case.applicant.full_name"]
        assert row.application_field == "application.applicant.name"
        assert row.application_field_label
        assert "731" in row.application_field_label

    def test_every_application_field_has_a_label(self, rows):
        for row in rows.values():
            if row.application_field:
                assert row.application_field_label, row.application_field

    def test_rows_without_application_field_need_no_label(self, rows):
        row = rows["case.applicant.short_name"]
        assert row.application_field is None
