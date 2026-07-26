"""Извлечение реквизитов из выписки ЕГРИП и маппинг для заявителя-ИП.

Проверяется на обезличенной фикстуре, повторяющей структуру настоящей
выписки: те же ловушки (ОГРНИП вразрядку, множество 15-значных ГРН,
ФИО тремя строками, повтор «Дата регистрации»).
"""

from __future__ import annotations

import pytest

from app.document_processing.extractors import extract_registry_fields
from app.document_processing.mappers import build_reconciliation
from app.infrastructure.database.models import FieldStatus
from tests.fixtures.egrip_sample import EGRIP_PAGES, EXPECTED


@pytest.fixture(scope="module")
def extracted():
    return extract_registry_fields(EGRIP_PAGES, "egrip")


def _by_field(extracted):
    return {r.field_id: r for r in extracted}


class TestEgripExtraction:
    def test_full_name_from_header(self, extracted):
        row = _by_field(extracted)["registry.sole_proprietor.full_name"]
        assert row.normalized_value == EXPECTED["full_name"]

    def test_name_parts_do_not_swallow_neighbours(self, extracted):
        """Фамилия/Имя/Отчество идут подряд без номеров строк."""
        by = _by_field(extracted)
        assert by["registry.sole_proprietor.last_name"].normalized_value == EXPECTED["last_name"]
        assert by["registry.sole_proprietor.first_name"].normalized_value == EXPECTED["first_name"]
        assert by["registry.sole_proprietor.middle_name"].normalized_value == EXPECTED["middle_name"]

    def test_ogrnip_is_taken_from_table_not_grn(self, extracted):
        """Среди множества 15-значных ГРН выбирается именно ОГРНИП."""
        row = _by_field(extracted)["registry.sole_proprietor.ogrnip"]
        assert row.normalized_value == EXPECTED["ogrnip"]
        assert row.validation_error is None

    def test_inn_is_twelve_digits(self, extracted):
        row = _by_field(extracted)["registry.sole_proprietor.inn"]
        assert row.normalized_value == EXPECTED["inn"]
        assert row.validation_error is None

    def test_registration_date_is_not_the_pfr_one(self, extracted):
        """«Дата регистрации» повторяется у страхователя ПФР — берётся ИП."""
        row = _by_field(extracted)["registry.sole_proprietor.registration_date"]
        assert row.normalized_value == EXPECTED["registration_date"]

    def test_main_activity_is_captured(self, extracted):
        row = _by_field(extracted)["registry.sole_proprietor.main_activity"]
        assert "47.91.2" in (row.normalized_value or "")

    def test_extract_number_starts_with_ie(self, extracted):
        row = _by_field(extracted)["registry.extract.number"]
        assert row.normalized_value == EXPECTED["extract_number"]

    def test_all_required_fields_extracted_cleanly(self, extracted):
        by = _by_field(extracted)
        for field_id in (
            "registry.sole_proprietor.full_name",
            "registry.sole_proprietor.ogrnip",
            "registry.sole_proprietor.inn",
        ):
            assert by[field_id].status is FieldStatus.matched, field_id
            assert by[field_id].validation_error is None, field_id


class TestSoleProprietorMapping:
    """Извлечённые поля ИП должны сверяться с полями заявления."""

    def test_sole_proprietor_rows_are_present(self, extracted):
        rows, _ = build_reconciliation(extracted, client_type="sole_proprietor")
        by_case = {r.case_field: r for r in rows}

        assert by_case["case.applicant.full_name"].registry_value == EXPECTED["full_name"]
        assert by_case["case.applicant.inn"].registry_value == EXPECTED["inn"]
        assert by_case["case.applicant.ogrn"].registry_value == EXPECTED["ogrnip"]

    def test_company_rows_are_hidden_for_sole_proprietor(self, extracted):
        """Заявителю-ИП не показываются поля юрлица (КПП и т. п.)."""
        rows, _ = build_reconciliation(extracted, client_type="sole_proprietor")
        registry_fields = {r.registry_field for r in rows}
        assert "registry.legal_entity.kpp" not in registry_fields
        assert "registry.legal_entity.full_name" not in registry_fields

    def test_address_is_manual_for_sole_proprietor(self, extracted):
        """Адрес ИП в выписке скрыт — строка есть, но без источника."""
        rows, _ = build_reconciliation(extracted, client_type="sole_proprietor")
        by_case = {r.case_field: r for r in rows}
        address = by_case["case.applicant.legal_address"]
        assert address.registry_field is None
        assert address.status is FieldStatus.missing

    def test_company_type_does_not_show_sole_proprietor_rows(self, extracted):
        """Обратная сторона роутинга: юрлицу не показываются поля ИП."""
        rows, _ = build_reconciliation(extracted, client_type="company")
        registry_fields = {r.registry_field for r in rows}
        assert "registry.sole_proprietor.ogrnip" not in registry_fields
