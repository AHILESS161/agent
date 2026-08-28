"""Метрики извлечения на обезличенном eval-наборе реестровых выписок."""

from app.document_processing.registry_evaluation import evaluate_registry_extraction
from tests.fixtures.egrip_sample import EGRIP_PAGES, EXPECTED as EGRIP_EXPECTED
from tests.fixtures.egrul_sample import EGRUL_PAGES, EXPECTED as EGRUL_EXPECTED


EGRUL_GOLD = {
    "registry.legal_entity.full_name": EGRUL_EXPECTED["full_name"],
    "registry.legal_entity.ogrn": EGRUL_EXPECTED["ogrn"],
    "registry.legal_entity.inn": EGRUL_EXPECTED["inn"],
    "registry.legal_entity.kpp": EGRUL_EXPECTED["kpp"],
    "registry.legal_entity.registration_date": EGRUL_EXPECTED["registration_date"],
    "registry.legal_entity.director.last_name": EGRUL_EXPECTED["director_last_name"],
    "registry.legal_entity.director.position": EGRUL_EXPECTED["director_position"],
}
EGRUL_REQUIRED = tuple(EGRUL_GOLD)[:4]

EGRIP_GOLD = {
    "registry.sole_proprietor.full_name": EGRIP_EXPECTED["full_name"],
    "registry.sole_proprietor.ogrnip": EGRIP_EXPECTED["ogrnip"],
    "registry.sole_proprietor.inn": EGRIP_EXPECTED["inn"],
    "registry.sole_proprietor.registration_date": EGRIP_EXPECTED["registration_date"],
}
EGRIP_REQUIRED = tuple(EGRIP_GOLD)[:3]


def test_clean_egrul_has_measurable_per_field_quality():
    report = evaluate_registry_extraction(
        EGRUL_PAGES,
        "egrul",
        EGRUL_GOLD,
        required_fields=EGRUL_REQUIRED,
    )

    assert report.exact_match_rate == 1.0
    assert report.required_match_rate == 1.0
    assert report.safe_to_prefill is True
    assert report.manual_review_fields == ()


def test_clean_egrip_has_measurable_per_field_quality():
    report = evaluate_registry_extraction(
        EGRIP_PAGES,
        "egrip",
        EGRIP_GOLD,
        required_fields=EGRIP_REQUIRED,
    )

    assert report.exact_match_rate == 1.0
    assert report.safe_to_prefill is True


def test_bad_ocr_does_not_silently_pass_as_safe_prefill():
    damaged = [
        (page, text.replace("19 ИНН", "19 ИHН").replace("20 КПП", "20 KПП"))
        for page, text in EGRUL_PAGES
    ]
    report = evaluate_registry_extraction(
        damaged,
        "egrul",
        EGRUL_GOLD,
        required_fields=EGRUL_REQUIRED,
    )

    assert report.safe_to_prefill is False
    assert "registry.legal_entity.inn" in report.manual_review_fields
    assert "registry.legal_entity.kpp" in report.manual_review_fields
    assert report.missing_fields >= 2


def test_conflict_is_sent_to_manual_review_even_if_best_value_matches():
    pages = list(EGRUL_PAGES)
    pages.append((4, "13 ОГРН 1184205019129\nВыписка из ЕГРЮЛ\nСтраница 4 из 4"))
    report = evaluate_registry_extraction(
        pages,
        "egrul",
        EGRUL_GOLD,
        required_fields=EGRUL_REQUIRED,
    )

    assert report.safe_to_prefill is False
    assert "registry.legal_entity.ogrn" in report.manual_review_fields
    ogrn = next(
        row for row in report.fields if row.field_id == "registry.legal_entity.ogrn"
    )
    assert "несколько значений" in (ogrn.review_reason or "")


def test_report_can_be_serialized_for_ci_artifact():
    report = evaluate_registry_extraction(
        EGRIP_PAGES,
        "egrip",
        EGRIP_GOLD,
        required_fields=EGRIP_REQUIRED,
    )

    payload = report.to_dict()
    assert payload["document_kind"] == "egrip"
    assert payload["fields"][0]["field_id"].startswith("registry.")

