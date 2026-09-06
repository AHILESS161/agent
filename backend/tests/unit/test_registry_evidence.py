from types import SimpleNamespace
import pytest
from app.infrastructure.providers.rospatent import _normalise_status, _goods_text
from app.infrastructure.providers.rospatent_public import _status_of
from app.services.conflict_search import priority_relation
from app.document_processing.similarity import assess, goods_similarity


@pytest.mark.parametrize("text,expected", [("invalid", "cancelled"), ("inactive", "cancelled"),
    ("не действует", "cancelled"), ("expired", "expired"), ("", "unknown"), ("неизвестно", "unknown")])
def test_status_is_not_inferred_from_record_type_or_active_substring(text, expected):
    assert _normalise_status(text, "registration") == expected
    assert _normalise_status(text, "application") == expected


def test_public_unknown_status_and_expired_right_are_distinct():
    assert _status_of({}, "application") == "unknown"
    assert _status_of({"status_code": "2", "expiry_date": "2000-01-01"}, "registration") == "expired"


def test_goods_payload_never_uses_class_numbers_as_goods():
    assert _goods_text([9, 25]) == ""
    assert _goods_text([{"class_number": 9, "description": "компьютеры"}]) == "компьютеры"
    assert goods_similarity([9], [9], "компьютеры", "огнетушители") == 0
    assert goods_similarity([9], [42], "программное обеспечение", "программное обеспечение") == 1
    result = assess("ORBIT", "ORBIT", [9], [25], "компьютеры", "одежда")
    assert result.mark_similarity == 1 and not result.confusion_likely


@pytest.mark.parametrize("right,applicant,expected", [("2020-01-01", "2022-01-01", "earlier"),
    ("2022-01-01", "2020-01-01", "not_earlier"), (None, "2020-01-01", "unknown"),
    ("2020-01-01", "хочу приоритет", "unknown")])
def test_priority_requires_actual_comparable_dates(right, applicant, expected):
    assert priority_relation(SimpleNamespace(priority_date=None, filing_date=right), applicant) == expected
