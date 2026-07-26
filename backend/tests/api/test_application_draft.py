"""Тесты чернового заявления.

Главное правило: в документ попадают только подтверждённые значения,
а экспорт возможен лишь после утверждения специалистом. Черновик
юридически значимого документа не должен содержать непроверенных
данных и не должен уходить наружу как готовый.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from app.services import file_storage
from tests.conftest import login_headers

EGRUL_TEXT = (
    "ВЫПИСКА\n"
    "из Единого государственного реестра юридических лиц\n"
    "1 Полное наименование ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРИМЕР\n"
    "13 ОГРН 1027700132195\n"
    "19 ИНН 7707083893\n"
    "Сведения о регистрирующем органе\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        file_storage.settings, "FILE_STORAGE_PATH", str(tmp_path / "docs")
    )
    return tmp_path


@pytest.fixture
async def lawyer_auth(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("lawyer-draft@test.ru", UserRole.lawyer)
    return login_headers(client, "lawyer-draft@test.ru")


@pytest.fixture
def case_with_fields(client, lawyer_auth) -> int:
    """Дело с загруженной выпиской и извлечёнными полями."""
    client_id = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": 'ООО "Тест"'},
        headers=lawyer_auth,
    ).json()["id"]
    app_id = client.post(
        "/api/v1/applications",
        json={"client_id": client_id, "mark_name": "ТЕСТЗНАК"},
        headers=lawyer_auth,
    ).json()["id"]

    document = client.post(
        f"/api/v1/applications/{app_id}/source-documents",
        files={"file": ("выписка.txt", EGRUL_TEXT, "text/plain")},
        headers=lawyer_auth,
    ).json()
    client.post(
        f"/api/v1/source-documents/{document['id']}/extract", headers=lawyer_auth
    )
    return app_id


@pytest.mark.api
class TestDraftOnlyUsesConfirmedData:
    """Ключевое требование к черновику."""

    def test_unconfirmed_fields_are_not_filled(
        self, client, lawyer_auth, case_with_fields
    ):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        filled_labels = {item["label"] for item in draft["filled_fields"]}
        assert "ОГРН" not in filled_labels
        assert "ИНН" not in filled_labels

    def test_skipped_fields_explain_why(self, client, lawyer_auth, case_with_fields):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        assert draft["skipped_fields"]
        for item in draft["skipped_fields"]:
            assert item["reason"]

    def test_confirmed_field_appears_in_draft(
        self, client, lawyer_auth, case_with_fields
    ):
        fields = client.get(
            f"/api/v1/applications/{case_with_fields}/field-reconciliation",
            headers=lawyer_auth,
        ).json()
        ogrn = next(
            item for item in fields["items"] if item["label"] == "ОГРН"
        )
        client.post(
            f"/api/v1/extracted-fields/{ogrn['extracted_field_id']}/confirm",
            json={"action": "accept"},
            headers=lawyer_auth,
        )

        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        filled = {item["label"]: item["value"] for item in draft["filled_fields"]}
        assert filled.get("ОГРН") == "1027700132195"

    def test_filled_field_keeps_its_source(
        self, client, lawyer_auth, case_with_fields
    ):
        """Специалист должен видеть, откуда значение попало в документ."""
        fields = client.get(
            f"/api/v1/applications/{case_with_fields}/field-reconciliation",
            headers=lawyer_auth,
        ).json()
        inn = next(item for item in fields["items"] if item["label"] == "ИНН")
        client.post(
            f"/api/v1/extracted-fields/{inn['extracted_field_id']}/confirm",
            json={"action": "accept"},
            headers=lawyer_auth,
        )

        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        entry = next(i for i in draft["filled_fields"] if i["label"] == "ИНН")
        assert "regex" in entry["source"]


@pytest.mark.api
class TestVersioningAndProvenance:
    def test_each_generation_creates_new_version(
        self, client, lawyer_auth, case_with_fields
    ):
        first = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        second = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        assert second["version"] == first["version"] + 1

    def test_versions_are_listed(self, client, lawyer_auth, case_with_fields):
        client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        )
        client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        )

        listing = client.get(
            f"/api/v1/applications/{case_with_fields}/drafts", headers=lawyer_auth
        ).json()
        assert listing["total"] == 2

    def test_draft_records_template_and_mapping_versions(
        self, client, lawyer_auth, case_with_fields
    ):
        """Нужно знать, по какому бланку и маппингу собран документ."""
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        provenance = draft["provenance"]
        assert provenance["template_name"]
        assert provenance["schema_version"]
        assert provenance["mapping_version"] >= 1


@pytest.mark.api
class TestExportRequiresApproval:
    def test_export_blocked_before_approval(
        self, client, lawyer_auth, case_with_fields
    ):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        assert draft["can_export"] is False

        response = client.get(f"/api/v1/drafts/{draft['id']}/download", headers=lawyer_auth)
        assert response.status_code == 409
        assert "не утверждён" in response.json()["detail"]

    def test_export_allowed_after_approval(
        self, client, lawyer_auth, case_with_fields
    ):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        approved = client.post(
            f"/api/v1/drafts/{draft['id']}/approve", headers=lawyer_auth
        ).json()
        assert approved["status"] == "approved_by_specialist"
        assert approved["can_export"] is True

        response = client.get(f"/api/v1/drafts/{draft['id']}/download", headers=lawyer_auth)
        assert response.status_code == 200
        assert len(response.content) > 1000

    def test_download_marks_draft_exported(
        self, client, lawyer_auth, case_with_fields
    ):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        client.post(f"/api/v1/drafts/{draft['id']}/approve", headers=lawyer_auth)
        client.get(f"/api/v1/drafts/{draft['id']}/download", headers=lawyer_auth)

        listing = client.get(
            f"/api/v1/applications/{case_with_fields}/drafts", headers=lawyer_auth
        ).json()
        assert listing["items"][0]["status"] == "exported"

    async def test_manager_cannot_approve(
        self, client, api_user_factory, lawyer_auth, case_with_fields
    ):
        """Утверждение содержания документа — решение специалиста."""
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        await api_user_factory("manager-draft@test.ru", UserRole.manager)
        manager = login_headers(client, "manager-draft@test.ru")

        response = client.post(f"/api/v1/drafts/{draft['id']}/approve", headers=manager)
        assert response.status_code == 403


@pytest.mark.api
class TestOfficialBlank:
    """Черновик — это заполненный бланк Роспатента, а не своя форма."""

    def _render(self, filled, classes=None):
        from app.services.application_draft import (
            DraftContent,
            FilledField,
            render_docx,
        )

        content = DraftContent()
        content.filled = [
            FilledField(field_id=fid, label=fid, value=value, source="regex")
            for fid, value in filled.items()
        ]
        content.classes = classes or []

        class _App:
            id = 1
            mark_text = "ЗВЁЗДОЧКА"
            mark_name = "ЗВЁЗДОЧКА"

        return render_docx(content, _App())

    def _document(self, payload):
        import io

        import docx

        return docx.Document(io.BytesIO(payload))

    def test_structure_of_the_blank_is_preserved(self):
        """Бланк остаётся бланком: та же таблица, те же строки."""
        document = self._document(self._render({}))
        assert len(document.tables) == 1
        assert len(document.tables[0].rows) == 118

    def test_applicant_lands_in_field_731(self):
        payload = self._render(
            {
                "application.applicant.name": "ООО «ПРИМЕР»",
                "application.applicant.address": "101000, Москва",
            }
        )
        text = self._document(payload).tables[0].rows[5].cells[0].text
        assert "ООО «ПРИМЕР»" in text
        assert "101000, Москва" in text

    def test_identifiers_land_in_their_block(self):
        payload = self._render(
            {
                "application.applicant.ogrn": "1027700132195",
                "application.applicant.inn": "7707083893",
            }
        )
        text = self._document(payload).tables[0].rows[5].cells[31].text
        assert "ОГРН: 1027700132195" in text
        assert "ИНН: 7707083893" in text

    def test_mark_lands_in_field_540(self):
        payload = self._render({"application.mark.text": "ЗВЁЗДОЧКА"})
        text = self._document(payload).tables[0].rows[17].cells[2].text
        assert "ЗВЁЗДОЧКА" in text

    def test_classes_fill_the_goods_table(self):
        payload = self._render({}, classes=[("25", "Одежда; обувь")])
        rows = self._document(payload).tables[0].rows
        assert "25" in rows[44].cells[0].text
        assert "Одежда" in rows[44].cells[3].text

    def test_no_service_notes_inside_the_document(self):
        """В бланке заявления не должно быть пометок про черновик и AI."""
        payload = self._render({"application.mark.text": "ЗВЁЗДОЧКА"})
        document = self._document(payload)
        full = "\n".join(p.text for p in document.paragraphs)
        full += "\n".join(
            cell.text for row in document.tables[0].rows for cell in row.cells
        )

        for forbidden in ("ЧЕРНОВИК", " AI ", "искусственн", "автоматически"):
            assert forbidden not in full, forbidden

    def test_unconfirmed_fields_stay_empty(self):
        """Незаполненное поле остаётся пустым, как в бумажной форме."""
        document = self._document(self._render({}))
        identifiers = document.tables[0].rows[5].cells[31].text
        assert "ОГРН:" in identifiers
        assert "1027700132195" not in identifiers


@pytest.mark.api
class TestChecklist:
    def test_checklist_lists_manual_steps(self, client, lawyer_auth, case_with_fields):
        """Чекбоксы бланка не определяются автоматически — это в чек-листе."""
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()

        text = " ".join(draft["checklist"])
        assert "550" in text
        assert "вручную" in text

    def test_checklist_mentions_missing_image(
        self, client, lawyer_auth, case_with_fields
    ):
        draft = client.post(
            f"/api/v1/applications/{case_with_fields}/draft", headers=lawyer_auth
        ).json()
        assert any("540" in item for item in draft["checklist"])


@pytest.mark.api
class TestAuth:
    def test_generation_requires_auth(self, client, case_with_fields):
        assert (
            client.post(f"/api/v1/applications/{case_with_fields}/draft").status_code
            == 401
        )

    def test_download_requires_auth(self, client):
        assert client.get("/api/v1/drafts/1/download").status_code == 401
