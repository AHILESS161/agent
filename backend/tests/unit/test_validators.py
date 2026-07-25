"""Тесты валидаторов российских реквизитов.

Все значения синтетические. Реквизиты из приложенных к репозиторию
документов сюда не копируются.

Контрольные суммы рассчитаны по действующим алгоритмам ФНС.
"""

from __future__ import annotations

import pytest

from app.document_processing.validators import (
    parse_ru_date,
    validate_date,
    validate_inn,
    validate_inn_individual,
    validate_inn_legal_entity,
    validate_kpp,
    validate_ogrn,
    validate_ogrnip,
)


class TestInn:
    # Синтетические ИНН с корректными контрольными суммами.
    VALID_10 = ["7707083893", "5024002119", "7736050003"]
    VALID_12 = ["500100732259", "773173322355"]

    @pytest.mark.parametrize("value", VALID_10)
    def test_accepts_valid_legal_entity_inn(self, value):
        assert validate_inn(value).ok
        assert validate_inn_legal_entity(value).ok

    @pytest.mark.parametrize("value", VALID_12)
    def test_accepts_valid_individual_inn(self, value):
        assert validate_inn(value).ok
        assert validate_inn_individual(value).ok

    def test_rejects_wrong_checksum_10(self):
        """Меняем последнюю цифру — контрольная сумма ломается."""
        result = validate_inn("7707083894")
        assert not result.ok
        assert "контрольная сумма" in result.error

    def test_rejects_wrong_checksum_12(self):
        assert not validate_inn("500100732258").ok

    @pytest.mark.parametrize("value", ["123456789", "12345678901", "1", ""])
    def test_rejects_wrong_length(self, value):
        assert not validate_inn(value).ok

    def test_rejects_non_digits(self):
        assert not validate_inn("77070838AB").ok

    def test_length_expectation_is_enforced(self):
        """ИНН физлица не должен пройти как ИНН организации."""
        assert not validate_inn_legal_entity("500100732259").ok
        assert not validate_inn_individual("7707083893").ok

    def test_tolerates_spaces(self):
        """В выписке значения печатаются вразрядку."""
        assert validate_inn_legal_entity("7 7 0 7 0 8 3 8 9 3").ok


class TestOgrn:
    VALID_OGRN = ["1027700132195", "1037746123128", "1184205019129"]

    @pytest.mark.parametrize("value", VALID_OGRN)
    def test_accepts_valid_ogrn(self, value):
        assert validate_ogrn(value).ok, value

    def test_rejects_wrong_checksum(self):
        result = validate_ogrn("1027700132196")
        assert not result.ok
        assert "контрольная сумма" in result.error

    @pytest.mark.parametrize("value", ["102770013219", "10277001321955"])
    def test_rejects_wrong_length(self, value):
        assert not validate_ogrn(value).ok

    def test_rejects_leading_zero(self):
        assert not validate_ogrn("0027700132195").ok

    def test_tolerates_spaced_digits(self):
        """На титульном листе выписки ОГРН печатается вразрядку."""
        assert validate_ogrn("1 1 8 4 2 0 5 0 1 9 1 2 9").ok

    def test_grn_record_number_is_not_a_valid_ogrn_by_luck(self):
        """Номера ГРН — тоже 13 цифр; проверяем, что валидатор их отличает
        по контрольной сумме, а не пропускает всё подряд."""
        # Заведомо испорченный номер той же длины.
        assert not validate_ogrn("2184205537955").ok


class TestSyntheticIdentifiersInSampleForms:
    """Реквизиты в образцах бланков — вымышленные и не проходят проверку.

    Это ожидаемое поведение: приложенный к репозиторию образец заявки
    заполнен демонстрационными значениями. Система обязана пометить их
    как требующие проверки, а не принять и не отбросить молча.
    """

    def test_sample_application_inn_fails_checksum(self):
        assert not validate_inn_legal_entity("7736777555").ok

    def test_sample_application_ogrn_fails_checksum(self):
        assert not validate_ogrn("1037746123123").ok

    def test_failure_reports_reason_for_the_specialist(self):
        result = validate_ogrn("1037746123123")
        assert result.error
        assert "контрольная сумма" in result.error


class TestOgrnip:
    def test_accepts_valid_ogrnip(self):
        assert validate_ogrnip("304500116000157").ok

    def test_rejects_wrong_checksum(self):
        assert not validate_ogrnip("304500116000158").ok

    def test_rejects_ogrn_length(self):
        """13-значный ОГРН не должен проходить как 15-значный ОГРНИП."""
        assert not validate_ogrnip("1027700132195").ok


class TestKpp:
    @pytest.mark.parametrize("value", ["770701001", "420501001", "5024AB001"])
    def test_accepts_valid_kpp(self, value):
        assert validate_kpp(value).ok, value

    @pytest.mark.parametrize("value", ["77070100", "7707010011", ""])
    def test_rejects_wrong_length(self, value):
        assert not validate_kpp(value).ok


class TestDates:
    def test_parses_russian_date(self):
        assert parse_ru_date("27.09.2018").isoformat() == "2018-09-27"

    def test_extracts_date_from_surrounding_text(self):
        assert parse_ru_date("Дата регистрации 27.09.2018 г.") is not None

    def test_returns_none_for_garbage(self):
        assert parse_ru_date("не дата") is None

    def test_rejects_future_date(self):
        result = validate_date("01.01.2099")
        assert not result.ok
        assert "будущем" in result.error

    def test_rejects_impossible_date(self):
        assert not validate_date("32.13.2020").ok

    def test_rejects_pre_1991_date(self):
        """До 1991 года ЕГРЮЛ не существовал — вероятна ошибка распознавания."""
        assert not validate_date("01.01.1985").ok

    def test_accepts_plausible_date(self):
        assert validate_date("27.09.2018").ok
