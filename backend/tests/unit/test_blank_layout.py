"""Разметка бланка заявления для интерактивного просмотра.

Специалист должен видеть заявление в структуре официальной формы:
те же разделы, тот же порядок, те же коды INID. Разметка описана
декларативно и проверяется на соответствие настоящему бланку.
"""

from __future__ import annotations

import docx
import pytest

from app.services.application_draft import (
    TEMPLATE_PATH,
    DraftContent,
    FilledField,
)
from app.services.blank_layout import build_form, load_layout


@pytest.fixture(scope="module")
def blank_text() -> str:
    document = docx.Document(str(TEMPLATE_PATH))
    return " ".join(
        " ".join(cell.text.split())
        for row in document.tables[0].rows
        for cell in row.cells
    )


class TestLayoutMatchesTheBlank:
    def test_layout_is_versioned(self):
        assert load_layout()["version"] >= 1

    def test_every_inid_code_exists_in_the_blank(self, blank_text):
        """Код, которого нет в форме, — ошибка разметки."""
        for section in load_layout()["sections"]:
            for field in section["fields"]:
                if field.get("inid"):
                    assert f"({field['inid']})" in blank_text, field["inid"]

    def test_key_sections_are_present(self):
        titles = {s["id"] for s in load_layout()["sections"]}
        assert {"applicant", "mark", "goods", "priority"} <= titles

    def test_sections_follow_the_blank_order(self):
        """Порядок разделов повторяет форму: заявитель → представитель
        → обозначение → перечень товаров → приоритет."""
        order = [s["id"] for s in load_layout()["sections"]]
        for earlier, later in (
            ("applicant", "representative"),
            ("representative", "mark"),
            ("mark", "goods"),
            ("goods", "priority"),
        ):
            assert order.index(earlier) < order.index(later)


class TestValues:
    def _content(self, **values) -> DraftContent:
        content = DraftContent()
        content.filled = [
            FilledField(field_id=key, label=key, value=value, source="regex")
            for key, value in values.items()
        ]
        return content

    def test_confirmed_values_are_placed(self):
        form = build_form(
            self._content(**{"application.applicant.name": "ООО «ПРИМЕР»"})
        )
        applicant = next(s for s in form["sections"] if s["id"] == "applicant")
        name = applicant["fields"][0]

        assert name["value"] == "ООО «ПРИМЕР»"
        assert name["is_filled"] is True

    def test_unconfirmed_fields_stay_empty(self):
        form = build_form(DraftContent())
        assert form["filled_count"] == 0
        for section in form["sections"]:
            for field in section["fields"]:
                assert field["value"] is None

    def test_classes_are_rendered_as_a_list(self):
        content = DraftContent()
        content.classes = [("25", "Одежда"), ("35", "Реклама")]
        form = build_form(content)

        goods = next(s for s in form["sections"] if s["id"] == "goods")
        assert "Класс 25" in goods["fields"][0]["value"]
        assert "Класс 35" in goods["fields"][0]["value"]


class TestFillModes:
    def test_office_fields_are_not_editable(self):
        """Регистрационный номер проставляет Роспатент."""
        form = build_form(DraftContent())
        office = next(s for s in form["sections"] if s["id"] == "office")
        assert all(f["editable"] is False for f in office["fields"])

    def test_mark_kind_is_a_checkbox(self):
        """Вид знака отмечается галочкой и определяется только вручную."""
        form = build_form(DraftContent())
        mark = next(s for s in form["sections"] if s["id"] == "mark")
        kind = next(f for f in mark["fields"] if f["inid"] == "550")
        assert kind["fill"] == "checkbox"

    def test_priority_is_manual(self):
        """Приоритет заявляется отдельно и из документов не берётся."""
        form = build_form(DraftContent())
        priority = next(s for s in form["sections"] if s["id"] == "priority")
        assert all(f["fill"] == "manual" for f in priority["fields"])

    def test_manual_fields_explain_themselves(self):
        """Поле без автоисточника должно объяснять, почему оно пустое."""
        form = build_form(DraftContent())
        mark = next(s for s in form["sections"] if s["id"] == "mark")
        kind = next(f for f in mark["fields"] if f["inid"] == "550")
        assert kind["hint"]


class TestFieldsDependOnApplicantType:
    """У юрлица, предпринимателя и физлица разные поля.

    Сверка полей больше не отдельная вкладка, поэтому набор полей
    в бланке должен покрывать все сведения по каждому типу — иначе
    их негде будет заполнить.
    """

    def _form(self, client_type: str):
        from app.document_processing.mappers import build_reconciliation

        rows, _ = build_reconciliation([], client_type=client_type)
        return build_form(DraftContent(), rows, client_type=client_type)

    def _labels(self, client_type: str) -> set[str]:
        form = self._form(client_type)
        return {
            field["label"]
            for section in form["sections"]
            for field in section["fields"]
        }

    def test_company_has_ogrn_and_kpp(self):
        labels = self._labels("company")
        assert "ОГРН" in labels
        assert "КПП" in labels

    def test_sole_proprietor_has_ogrnip(self):
        assert "ОГРНИП" in self._labels("sole_proprietor")

    def test_individual_has_passport(self):
        """Паспортные поля в бланк не переносятся, но заполнять их надо."""
        labels = self._labels("individual")
        assert any("Паспорт" in label for label in labels)

    def test_individual_has_no_company_fields(self):
        labels = self._labels("individual")
        assert "ОГРН" not in labels
        assert "КПП" not in labels

    def test_sole_proprietor_has_no_director(self):
        assert not any(
            "руководител" in label.lower()
            for label in self._labels("sole_proprietor")
        )

    def test_required_fields_are_counted(self):
        """Специалист должен видеть, сколько обязательных не закрыто."""
        form = self._form("company")
        assert form["required_count"] > 0
        assert form["can_generate"] is False
        assert form["blocking"]
