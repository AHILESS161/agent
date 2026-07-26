"""Тесты детерминированного извлечения реквизитов из выписки ЕГРЮЛ.

Работают на обезличенной фикстуре, воспроизводящей структуру и ловушки
настоящей выписки. LLM в этом контуре не участвует.
"""

from __future__ import annotations

import pytest

from app.document_processing.extractors import extract_registry_fields
from app.infrastructure.database.models import ExtractionMethod, FieldStatus
from tests.fixtures.egrul_sample import EGRUL_PAGES, EXPECTED, TRAPS


@pytest.fixture(scope="module")
def fields() -> dict:
    results = extract_registry_fields(EGRUL_PAGES)
    return {r.field_id: r for r in results}


def _value(fields: dict, short_id: str) -> str | None:
    return fields[f"registry.legal_entity.{short_id}"].normalized_value


class TestCoreIdentifiers:
    def test_extracts_full_name_across_multiple_lines(self, fields):
        """Наименование занимает три строки таблицы."""
        assert _value(fields, "full_name") == EXPECTED["full_name"]

    def test_extracts_short_name(self, fields):
        assert _value(fields, "short_name") == EXPECTED["short_name"]

    def test_extracts_ogrn(self, fields):
        assert _value(fields, "ogrn") == EXPECTED["ogrn"]

    def test_extracts_inn(self, fields):
        assert _value(fields, "inn") == EXPECTED["inn"]

    def test_extracts_kpp(self, fields):
        assert _value(fields, "kpp") == EXPECTED["kpp"]

    def test_all_core_fields_use_regex_not_llm(self, fields):
        for short_id in ("full_name", "ogrn", "inn", "kpp"):
            field = fields[f"registry.legal_entity.{short_id}"]
            assert field.extraction_method is ExtractionMethod.regex


class TestTraps:
    """Проверки, что извлекатель не попадается на однотипные значения."""

    def test_ogrn_is_not_confused_with_grn_record_numbers(self, fields):
        """Номера ГРН — тоже 13 цифр и встречаются в выписке многократно."""
        assert _value(fields, "ogrn") not in TRAPS["grn_record_numbers"]

    def test_company_inn_is_not_confused_with_director_inn(self, fields):
        assert _value(fields, "inn") != TRAPS["director_inn"]

    def test_company_inn_is_not_confused_with_founder_inn(self, fields):
        assert _value(fields, "inn") != TRAPS["founder_inn"]

    def test_company_inn_has_ten_digits(self, fields):
        """У организации ИНН 10-значный, у физлиц — 12-значный."""
        assert len(_value(fields, "inn")) == 10

    def test_director_is_not_confused_with_founders(self, fields):
        """Подписи «Фамилия/Имя/Отчество» одинаковы у руководителя
        и у учредителей — различает только раздел документа."""
        last_name = _value(fields, "director.last_name")
        assert last_name == EXPECTED["director_last_name"]
        assert last_name.upper() not in TRAPS["founder_last_names"]

    def test_registration_date_is_not_confused_with_fund_dates(self, fields):
        """«Дата регистрации» встречается трижды: организация, ПФР, ФСС."""
        value = _value(fields, "registration_date")
        assert value == EXPECTED["registration_date"]
        assert value != TRAPS["pension_fund_date"]
        assert value != TRAPS["social_fund_date"]


class TestTraceability:
    def test_every_extracted_field_reports_page_number(self, fields):
        for field in fields.values():
            if field.status is FieldStatus.matched:
                assert field.page_number is not None, field.field_id

    def test_page_numbers_are_correct(self, fields):
        """ОГРН — на первой странице, ИНН — на второй."""
        assert fields["registry.legal_entity.ogrn"].page_number == 1
        assert fields["registry.legal_entity.inn"].page_number == 2
        assert fields["registry.legal_entity.director.last_name"].page_number == 2

    def test_every_extracted_field_reports_pattern_id(self, fields):
        for field in fields.values():
            if field.status is FieldStatus.matched:
                assert field.pattern_id, field.field_id

    def test_every_extracted_field_keeps_source_snippet(self, fields):
        for field in fields.values():
            if field.status is FieldStatus.matched:
                assert field.source_snippet, field.field_id

    def test_confidence_is_reported_and_never_absolute(self, fields):
        for field in fields.values():
            if field.status is FieldStatus.matched:
                assert field.confidence is not None
                assert 0 < field.confidence < 1.0, field.field_id


class TestNormalisation:
    def test_spaced_ogrn_on_title_page_is_handled(self, fields):
        """На титульном листе ОГРН напечатан вразрядку."""
        assert _value(fields, "ogrn").isdigit()
        assert len(_value(fields, "ogrn")) == 13

    def test_normalisation_change_is_recorded(self, fields):
        """Преобразование значения не должно происходить молча."""
        name = fields["registry.legal_entity.full_name"]
        assert name.normalization_changed is True
        assert name.value != name.normalized_value

    def test_person_name_is_converted_from_caps(self, fields):
        """В ЕГРЮЛ ФИО прописными, в заявлении — обычным написанием."""
        assert _value(fields, "director.last_name") == "Петров"

    def test_address_is_composed_from_parts(self, fields):
        composed = _value(fields, "address.full")
        assert composed.startswith(EXPECTED["postal_code"])
        for part in ("ГОРОД МОСКВА", "УЛИЦА ТЕСТОВАЯ", "ДОМ 7", "ОФИС 101"):
            assert part in composed

    def test_composed_address_is_less_confident_than_read_values(self, fields):
        """Собранное по правилу значение надёжнее не становится."""
        composed = fields["registry.legal_entity.address.full"]
        postal = fields["registry.legal_entity.address.postal_code"]
        assert composed.confidence < postal.confidence


class TestConflictHandling:
    def test_corroboration_is_not_treated_as_conflict(self, fields):
        """ОГРН встречается и в таблице, и в колонтитуле — значение одно.

        Повторы сводятся к одному кандидату: предлагать выбор между
        одинаковыми строками бессмысленно. Сам факт повтора сохраняется
        списком страниц и повышает уверенность.
        """
        ogrn = fields["registry.legal_entity.ogrn"]
        assert ogrn.status is FieldStatus.matched
        assert len(ogrn.candidates) == 1
        assert len(ogrn.candidates[0].pages) > 1

    def test_corroboration_raises_confidence(self, fields):
        ogrn = fields["registry.legal_entity.ogrn"]
        best_single = max(c.confidence for c in ogrn.candidates)
        assert ogrn.confidence > best_single

    def test_conflicting_values_are_all_preserved(self):
        """При несовпадающих значениях сохраняются все кандидаты."""
        text = (
            "13 ОГРН 1027700132195\n"
            "Выписка из ЕГРЮЛ\n"
            "01.03.2024 09:00:00 ОГРН 1184205019129 Страница 1 из 1"
        )
        results = {r.field_id: r for r in extract_registry_fields([(1, text)])}
        ogrn = results["registry.legal_entity.ogrn"]

        assert ogrn.status is FieldStatus.conflict
        assert len({c.normalized_value for c in ogrn.candidates}) == 2
        assert "требуется выбор специалиста" in ogrn.validation_error

    def test_missing_required_field_is_flagged(self):
        results = {r.field_id: r for r in extract_registry_fields([(1, "пустой текст")])}
        name = results["registry.legal_entity.full_name"]
        assert name.status is FieldStatus.missing
        assert name.required is True
        assert name.validation_error


class TestValidationIntegration:
    def test_invalid_checksum_marks_field_for_review(self):
        """Значение с битой контрольной суммой не принимается молча."""
        text = "13 ОГРН 1027700132196\n"
        results = {r.field_id: r for r in extract_registry_fields([(1, text)])}
        ogrn = results["registry.legal_entity.ogrn"]

        assert ogrn.status is FieldStatus.needs_review
        assert "контрольная сумма" in ogrn.validation_error

    def test_valid_checksum_is_matched(self, fields):
        assert fields["registry.legal_entity.ogrn"].status is FieldStatus.matched
        assert fields["registry.legal_entity.ogrn"].validation_error is None


class TestPrivacy:
    def test_director_fields_are_marked_sensitive(self, fields):
        for part in ("last_name", "first_name", "middle_name"):
            field = fields[f"registry.legal_entity.director.{part}"]
            assert field.is_sensitive is True, part

    def test_company_identifiers_are_not_marked_sensitive(self, fields):
        for short_id in ("ogrn", "inn", "kpp"):
            assert fields[f"registry.legal_entity.{short_id}"].is_sensitive is False

    def test_founder_personal_data_is_not_extracted(self, fields):
        """Персональные данные учредителей задаче не нужны."""
        extracted_values = {
            f.normalized_value for f in fields.values() if f.normalized_value
        }
        assert TRAPS["founder_inn"] not in extracted_values
        for name in TRAPS["founder_last_names"]:
            assert name.capitalize() not in extracted_values


class TestNothingIsAutoConfirmed:
    def test_no_field_is_returned_as_confirmed(self, fields):
        """Подтверждение — исключительно действие специалиста."""
        for field in fields.values():
            assert field.status is not FieldStatus.confirmed


class TestRepeatsAreNotAChoice:
    """Одно значение на нескольких страницах — подтверждение.

    Регрессия: ОГРНИП встречается в колонтитуле каждой страницы
    выписки, и интерфейс предлагал «выбрать верное» из пяти
    одинаковых строк.
    """

    def _extracted(self):
        from tests.fixtures.egrip_sample import EGRIP_PAGES

        results = extract_registry_fields(EGRIP_PAGES, "egrip")
        return {r.field_id: r for r in results}

    def test_duplicate_values_collapse_into_one_candidate(self):
        field = self._extracted()["registry.sole_proprietor.ogrnip"]
        values = {c.normalized_value for c in field.candidates}

        assert len(values) == 1
        assert len(field.candidates) == 1

    def test_pages_of_repeats_are_kept(self):
        """Совпадение на нескольких страницах — полезный признак."""
        field = self._extracted()["registry.sole_proprietor.ogrnip"]
        assert len(field.candidates[0].pages) >= 1

    def test_repeats_do_not_create_conflict(self):
        from app.infrastructure.database.models import FieldStatus

        field = self._extracted()["registry.sole_proprietor.ogrnip"]
        assert field.status is not FieldStatus.conflict
