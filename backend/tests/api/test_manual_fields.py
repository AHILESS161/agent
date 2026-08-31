"""Ручной ввод значений в сверке полей.

Не всё есть в документах: адрес места жительства ИП в выписке ЕГРИП
скрыт, часть сведений клиент сообщает письмом. Раньше такое поле
заполнить было негде — записи в базе у него нет, а значит нет и
кнопок. Теперь значение вносится вручную и сразу считается
подтверждённым: его ввёл человек.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def lawyer(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("manual@test.ru", UserRole.lawyer)
    return login_headers(client, "manual@test.ru")


@pytest.fixture
def case(client, lawyer) -> int:
    client_id = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": 'ООО "Тест"'},
        headers=lawyer,
    ).json()["id"]
    return client.post(
        "/api/v1/applications",
        json={"client_id": client_id, "mark_name": "ЗВЁЗДОЧКА"},
        headers=lawyer,
    ).json()["id"]


def _add(client, lawyer, case, **kwargs):
    payload = {
        "field_path": "registry.legal_entity.address.full",
        "label": "Адрес места нахождения",
        "value": "101000, г. Москва, ул. Тестовая, д. 1",
    }
    payload.update(kwargs)
    return client.post(f"/api/v1/applications/{case}/fields", json=payload, headers=lawyer)


@pytest.mark.api
class TestManualEntry:
    def test_value_can_be_entered_for_a_missing_field(self, client, lawyer, case):
        response = _add(client, lawyer, case)
        assert response.status_code == 201
        assert response.json()["normalized_value"].startswith("101000")

    def test_manual_value_is_confirmed(self, client, lawyer, case):
        """Проверять за человеком систему незачем."""
        assert _add(client, lawyer, case).json()["status"] == "confirmed"

    def test_source_is_recorded_as_manual(self, client, lawyer, case):
        """В документе должно быть видно происхождение значения."""
        assert _add(client, lawyer, case).json()["extraction_method"] == "manual"

    def test_repeated_entry_updates_instead_of_duplicating(
        self, client, lawyer, case
    ):
        first = _add(client, lawyer, case).json()
        second = _add(client, lawyer, case, value="Другой адрес").json()

        assert second["id"] == first["id"]
        assert second["normalized_value"] == "Другой адрес"

    def test_value_appears_in_reconciliation(self, client, lawyer, case):
        _add(client, lawyer, case)
        rows = client.get(
            f"/api/v1/applications/{case}/field-reconciliation", headers=lawyer
        ).json()["items"]

        address = next(
            r
            for r in rows
            if r["registry_field"] == "registry.legal_entity.address.full"
        )
        assert address["status"] == "confirmed"
        assert address["registry_value"].startswith("101000")

    def test_preview_edit_updates_application_source(self, client, lawyer, case):
        response = _add(
            client,
            lawyer,
            case,
            field_path="application.mark.description",
            label="Описание обозначения",
            value="Словесное обозначение выполнено кириллицей",
        )
        assert response.status_code == 201
        application = client.get(
            f"/api/v1/applications/{case}", headers=lawyer
        ).json()
        assert application["description_of_mark"] == "Словесное обозначение выполнено кириллицей"

        form = client.get(
            f"/api/v1/applications/{case}/draft-form", headers=lawyer
        ).json()
        field = next(
            item
            for section in form["sections"]
            for item in section["fields"]
            if item.get("source") == "application.mark.description"
        )
        assert field["value"] == "Словесное обозначение выполнено кириллицей"

    def test_preview_edit_updates_applicant_card(self, client, lawyer, case):
        response = _add(
            client,
            lawyer,
            case,
            field_path="application.applicant.name",
            label="Наименование заявителя",
            value='ООО "Новое наименование"',
        )
        assert response.status_code == 201
        application = client.get(
            f"/api/v1/applications/{case}", headers=lawyer
        ).json()
        applicant = client.get(
            f"/api/v1/clients/{application['client_id']}", headers=lawyer
        ).json()
        assert applicant["full_name_or_company_name"] == 'ООО "Новое наименование"'

    def test_preview_rejects_invalid_signature_date(self, client, lawyer, case):
        response = _add(
            client,
            lawyer,
            case,
            field_path="application.signatory.date",
            label="Дата подписания",
            value="завтра",
        )
        assert response.status_code == 422

    def test_preview_edit_invalidates_previous_data_confirmation(
        self, client, lawyer, case
    ):
        confirmed = client.post(
            f"/api/v1/applications/{case}/data-confirmation",
            headers=lawyer,
        )
        assert confirmed.status_code == 201
        assert confirmed.json()["confirmed"] is True

        _add(
            client,
            lawyer,
            case,
            field_path="application.mark.description",
            label="Описание обозначения",
            value="Обновлённое описание",
        )
        state = client.get(
            f"/api/v1/applications/{case}/data-confirmation",
            headers=lawyer,
        ).json()
        assert state["confirmed"] is False


@pytest.mark.api
class TestCustomField:
    def test_specialist_can_add_own_field(self, client, lawyer, case):
        response = _add(
            client,
            lawyer,
            case,
            field_path="custom.contact",
            label="Контактное лицо",
            value="Иванов И.И.",
        )
        assert response.status_code == 201

    def test_custom_field_is_visible_in_reconciliation(self, client, lawyer, case):
        """Иначе созданное поле исчезало бы сразу после сохранения."""
        _add(
            client,
            lawyer,
            case,
            field_path="custom.contact",
            label="Контактное лицо",
            value="Иванов И.И.",
        )
        rows = client.get(
            f"/api/v1/applications/{case}/field-reconciliation", headers=lawyer
        ).json()["items"]

        custom = [r for r in rows if r.get("is_custom")]
        assert len(custom) == 1
        assert custom[0]["label"] == "Контактное лицо"

    def test_custom_field_can_be_deleted(self, client, lawyer, case):
        created = _add(
            client,
            lawyer,
            case,
            field_path="custom.contact",
            label="Контактное лицо",
            value="Иванов И.И.",
        ).json()

        assert (
            client.delete(
                f"/api/v1/extracted-fields/{created['id']}", headers=lawyer
            ).status_code
            == 204
        )


@pytest.mark.api
class TestExtractedFieldsAreProtected:
    def test_extracted_field_cannot_be_deleted(self, client, lawyer, case):
        """Извлечённое поле отклоняют, а не стирают: решение должно
        остаться в истории."""
        document = client.post(
            f"/api/v1/applications/{case}/source-documents",
            files={
                "file": (
                    "выписка.txt",
                    (
                        "ВЫПИСКА\n"
                        "из Единого государственного реестра юридических лиц\n"
                        "13 ОГРН 1027700132195\n"
                        "Сведения о регистрирующем органе\n"
                    ).encode("utf-8"),
                    "text/plain",
                )
            },
            headers=lawyer,
        ).json()
        client.post(
            f"/api/v1/source-documents/{document['id']}/extract", headers=lawyer
        )

        fields = client.get(
            f"/api/v1/source-documents/{document['id']}/fields", headers=lawyer
        ).json()["items"]
        extracted = next(f for f in fields if f["extraction_method"] != "manual")

        response = client.delete(
            f"/api/v1/extracted-fields/{extracted['id']}", headers=lawyer
        )
        assert response.status_code == 409


@pytest.mark.api
class TestAccess:
    def test_manual_entry_requires_auth(self, client, case):
        response = client.post(
            f"/api/v1/applications/{case}/fields",
            json={"field_path": "custom.x", "label": "X", "value": "1"},
        )
        assert response.status_code == 401


@pytest.mark.api
class TestSkipField:
    """Ненужное в этом деле поле убирается из сверки."""

    def _skip(self, client, lawyer, case, field_path, label):
        return client.post(
            f"/api/v1/applications/{case}/fields/skip",
            json={"field_path": field_path, "label": label},
            headers=lawyer,
        )

    def test_optional_field_can_be_skipped(self, client, lawyer, case):
        response = self._skip(
            client,
            lawyer,
            case,
            "registry.legal_entity.director.last_name",
            "Фамилия руководителя",
        )
        assert response.status_code == 201
        assert response.json()["status"] == "left_empty"

    def test_required_field_cannot_be_skipped(self, client, lawyer, case):
        """Иначе заявление окажется неполным, а система это скроет."""
        response = self._skip(
            client, lawyer, case, "registry.legal_entity.inn", "ИНН"
        )
        assert response.status_code == 409
        assert "обязательно" in response.json()["detail"]

    def test_decision_is_visible_in_reconciliation(self, client, lawyer, case):
        self._skip(
            client,
            lawyer,
            case,
            "registry.legal_entity.director.last_name",
            "Фамилия руководителя",
        )
        rows = client.get(
            f"/api/v1/applications/{case}/field-reconciliation", headers=lawyer
        ).json()["items"]

        row = next(
            r
            for r in rows
            if r["registry_field"] == "registry.legal_entity.director.last_name"
        )
        assert row["status"] == "left_empty"

    def test_skip_can_be_undone(self, client, lawyer, case):
        """Решение не безвозвратное."""
        created = self._skip(
            client,
            lawyer,
            case,
            "registry.legal_entity.director.last_name",
            "Фамилия руководителя",
        ).json()

        assert (
            client.delete(
                f"/api/v1/extracted-fields/{created['id']}", headers=lawyer
            ).status_code
            == 204
        )
