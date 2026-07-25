"""Тесты схемы полей заявления.

Проверяется сохранённая в репозитории схема — она версионируется и
используется при генерации документов, поэтому её структура и заявленные
ограничения должны быть зафиксированы тестами.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "application_templates"
    / "trademark_application.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    if not SCHEMA_PATH.exists():
        pytest.skip(
            "Схема не сгенерирована. Выполните: "
            "python -m scripts.analyze_application_template <бланк.pdf>"
        )
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class TestProvenance:
    """Схема должна быть прослеживаема до исходного бланка."""

    def test_records_source_hash(self, schema):
        assert len(schema["source"]["sha256"]) == 64

    def test_records_source_filename_and_format(self, schema):
        assert schema["source"]["filename"]
        assert schema["source"]["format"] == "pdf"

    def test_records_schema_version(self, schema):
        assert schema["schema_version"]

    def test_records_analysis_date(self, schema):
        assert schema["analysed_at"]

    def test_declares_deterministic_analysis(self, schema):
        """Схема строится без LLM — это должно быть зафиксировано."""
        assert "LLM не использовался" in schema["analysis_method"]


class TestFields:
    def test_all_declared_fields_found_in_template(self, schema):
        missing = [f["field_id"] for f in schema["fields"] if not f["found_in_template"]]
        assert not missing, f"Не найдены в бланке: {missing}"

    def test_field_ids_are_unique(self, schema):
        ids = [f["field_id"] for f in schema["fields"]]
        assert len(ids) == len(set(ids))

    def test_key_inid_codes_are_present(self, schema):
        """Ключевые коды ВОИС ST.9 должны быть описаны."""
        codes = {f["inid_code"] for f in schema["fields"] if f["inid_code"]}
        for code in ("731", "740", "540", "571", "511", "550"):
            assert code in codes, code

    def test_applicant_subfields_exist_for_mapping(self, schema):
        """Блок (731) в бланке единый, но в маппинге нужны части."""
        ids = {f["field_id"] for f in schema["fields"]}
        assert "application.applicant.name" in ids
        assert "application.applicant.address" in ids

    def test_required_fields_are_marked(self, schema):
        required = [f for f in schema["fields"] if f["required"]]
        assert required

    def test_every_field_declares_position(self, schema):
        for f in schema["fields"]:
            assert "source_document_position" in f


class TestCheckboxes:
    """Отмеченность чекбоксов из PDF не определяется — они нарисованы
    векторными прямоугольниками и в текстовом слое отсутствуют."""

    def test_checkboxes_are_detected(self, schema):
        assert schema["statistics"]["checkboxes_detected"] > 0

    def test_every_checkbox_has_a_label(self, schema):
        assert schema["statistics"]["checkboxes_without_label"] == 0

    def test_no_checkbox_state_is_inferred(self, schema):
        for checkbox in schema["checkboxes"]:
            assert checkbox["state"] == "undetermined"

    def test_every_checkbox_requires_manual_confirmation(self, schema):
        for checkbox in schema["checkboxes"]:
            assert checkbox["manual_confirmation_required"] is True

    def test_every_checkbox_records_position(self, schema):
        for checkbox in schema["checkboxes"]:
            assert checkbox["page"] >= 1
            assert checkbox["position"]["width"] > 0

    def test_mark_kind_options_are_captured(self, schema):
        """Варианты вида знака нужны, чтобы специалист выбрал вручную."""
        labels = {(c["label"] or "").lower() for c in schema["checkboxes"]}
        for option in ("словесный знак", "изобразительный знак", "комбинированный знак"):
            assert option in labels, option


class TestManualConfirmation:
    def test_choice_and_boolean_fields_require_confirmation(self, schema):
        for f in schema["fields"]:
            if f["data_type"] in ("choice", "boolean"):
                assert f["manual_confirmation_required"] is True, f["field_id"]

    def test_image_field_requires_confirmation(self, schema):
        """(540) — область изображения, а не текст."""
        image_fields = [f for f in schema["fields"] if f["data_type"] == "image"]
        assert image_fields
        for f in image_fields:
            assert f["manual_confirmation_required"] is True


class TestLimitations:
    def test_limitations_are_documented(self, schema):
        assert schema["limitations"]

    def test_checkbox_limitation_is_stated(self, schema):
        text = " ".join(schema["limitations"]).lower()
        assert "чекбокс" in text
        assert "ручного подтверждения" in text or "вручную" in text

    def test_unresolved_items_are_listed(self, schema):
        """Нераспознанное перечисляется явно, а не замалчивается."""
        assert "unresolved" in schema
        assert isinstance(schema["unresolved"], list)
