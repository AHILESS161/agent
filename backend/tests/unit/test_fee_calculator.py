"""Тарифы пошлин за обычную заявку на товарный знак."""

import pytest

from app.services.fee_calculator import calculate_amounts


def test_one_class_has_base_fees_only():
    result = calculate_amounts(1)
    assert result == {
        "formal": 4000,
        "examination": 13000,
        "registration": 18000,
        "filing_total": 17000,
        "total_electronic": 35000,
    }


def test_each_class_over_first_increases_both_filing_payments():
    result = calculate_amounts(2)
    assert result["formal"] == 5000
    assert result["examination"] == 15500
    assert result["filing_total"] == 20500
    assert result["total_electronic"] == 38500


def test_registration_increases_only_after_five_classes():
    result = calculate_amounts(6)
    assert result["registration"] == 20000


def test_term_surcharge_is_added_to_examination():
    result = calculate_amounts(1, term_surcharge=1500)
    assert result["examination"] == 14500
    assert result["total_electronic"] == 36500


def test_zero_classes_cannot_be_calculated():
    with pytest.raises(ValueError):
        calculate_amounts(0)
