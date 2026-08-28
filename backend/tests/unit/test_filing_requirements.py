from types import SimpleNamespace

from app.services.filing_requirements import (
    applicant_identifier_fields,
    filing_requirements_manifest,
    missing_required_items,
)


def _application(
    applicant_type: str,
    *,
    mark_type: str = "word",
    priority: str | None = None,
):
    client = SimpleNamespace(
        type=applicant_type,
        full_name_or_company_name="Тестовый заявитель",
        address="Россия, Москва",
        inn="7707083893" if applicant_type == "company" else "771234567859",
        ogrn_or_ogrnip=(
            "1027700132195" if applicant_type == "company" else "315774600312340"
        ),
        kpp="770701001" if applicant_type == "company" else None,
        country="RU",
    )
    return SimpleNamespace(
        client=client,
        mark_name="ТЕСТ",
        mark_type=mark_type,
        goods_services_raw="Ремонт компьютеров",
        description_of_mark="Словесное обозначение",
        filing_method="electronic",
        signatory_name="Иванов Иван Иванович",
        signatory_position="Директор" if applicant_type == "company" else None,
        signature_date="2026-08-28",
        request_paper_certificate=False,
        territory="Российская Федерация",
        priority_claim=priority,
    )


def _by_code(manifest):
    return {item["code"]: item for item in manifest["requirements"]}


def test_company_fields_are_required_from_one_manifest():
    rules = _by_code(filing_requirements_manifest(_application("company")))
    assert rules["applicant_inn"]["required"] is True
    assert rules["applicant_registry_number"]["required"] is True
    assert rules["signatory_position"]["required"] is True


def test_individual_does_not_receive_company_requirements():
    rules = _by_code(filing_requirements_manifest(_application("individual")))
    assert rules["applicant_registry_number"]["applicable"] is False
    assert rules["applicant_kpp"]["applicable"] is False
    assert rules["signatory_position"]["applicable"] is False
    assert rules["applicant_inn"]["required"] is False


def test_combined_mark_requires_image_until_it_is_available():
    application = _application("sole_proprietor", mark_type="combined")
    missing = {item["code"] for item in missing_required_items(
        filing_requirements_manifest(application)
    )}
    assert "mark_image" in missing
    ready = _by_code(filing_requirements_manifest(
        application, available_attachments={"mark_image"}
    ))
    assert ready["mark_image"]["satisfied"] is True


def test_representative_and_priority_enable_conditional_attachments():
    rules = _by_code(filing_requirements_manifest(
        _application("company", priority="convention"),
        has_representative=True,
    ))
    assert rules["power_of_attorney"]["required"] is True
    assert rules["priority_proof"]["required"] is True


def test_docx_identifier_labels_use_the_same_catalog():
    assert applicant_identifier_fields("sole_proprietor")[0][0] == "ОГРНИП"
    individual = applicant_identifier_fields("individual")
    assert individual == (("ИНН", "application.applicant.inn"),)


def test_filing_method_selects_the_correct_signature_instruction():
    electronic = _by_code(filing_requirements_manifest(_application("company")))
    assert electronic["electronic_signature_notice"]["applicable"] is True
    assert electronic["paper_signature_notice"]["applicable"] is False

    paper_application = _application("company")
    paper_application.filing_method = "paper"
    paper = _by_code(filing_requirements_manifest(paper_application))
    assert paper["paper_signature_notice"]["applicable"] is True
    assert paper["electronic_signature_notice"]["applicable"] is False
