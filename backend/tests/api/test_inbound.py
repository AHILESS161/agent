"""Тесты приёма обращений.

Пока нет интеграции с CRM и почтой, обращение вносит юрист. Но путь
обработки общий для всех каналов, поэтому здесь же проверяется
идемпотентность: повторная доставка одного события не должна
создавать ни второго события, ни второго дела.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from app.services import file_storage
from tests.conftest import login_headers

VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

INTAKE = {
    "sender": "Петров П. П., petrov@example.ru",
    "subject": "Регистрация знака",
    "body_text": "Хотим зарегистрировать знак для нашей продукции.",
    "create_case": True,
    "new_client": {
        "type": "company",
        "full_name_or_company_name": 'ООО «Пример»',
        "inn": "7707083893",
    },
    "mark_name": "ЗВЁЗДОЧКА",
    "mark_type": "word",
    "business_description": "Производство кондитерских изделий",
    "goods_services": "печенье, торты",
}


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        file_storage.settings, "FILE_STORAGE_PATH", str(tmp_path / "docs")
    )
    return tmp_path


@pytest.fixture
async def lawyer_auth(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("lawyer-inbound@test.ru", UserRole.lawyer)
    return login_headers(client, "lawyer-inbound@test.ru")


@pytest.mark.api
class TestIntakeRequiresAuth:
    def test_anonymous_cannot_create_intake(self, client):
        assert client.post("/api/v1/inbound/events", json=INTAKE).status_code == 401

    def test_anonymous_cannot_list_events(self, client):
        assert client.get("/api/v1/inbound/events").status_code == 401

    async def test_client_role_can_create_only_own_new_intake(self, client, api_user_factory):
        await api_user_factory("client-inbound@test.ru", UserRole.client)
        headers = login_headers(client, "client-inbound@test.ru")

        response = client.post("/api/v1/inbound/events", json=INTAKE, headers=headers)
        assert response.status_code == 201

        foreign_target = {**INTAKE, "new_client": None, "target_case_id": 999}
        forbidden = client.post(
            "/api/v1/inbound/events", json=foreign_target, headers=headers
        )
        assert forbidden.status_code == 403


@pytest.mark.api
class TestIntakeCreatesCase:
    def test_creates_event_and_case(self, client, lawyer_auth):
        response = client.post("/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth)
        assert response.status_code == 201

        body = response.json()
        assert body["is_duplicate"] is False
        assert body["status"] == "case_created"
        assert body["created_case_id"]

    def test_created_case_is_visible_in_lawyers_project_list(
        self, client, lawyer_auth
    ):
        """Входящее дело не должно становиться «ничьим» и пропадать с обзора."""
        created = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        projects = client.get(
            "/api/v1/applications?page=1&page_size=100", headers=lawyer_auth
        ).json()["items"]

        assert created["created_case_id"] in {item["id"] for item in projects}

    def test_case_keeps_business_description_for_class_selection(
        self, client, lawyer_auth
    ):
        """Описание деятельности нужно для подбора классов МКТУ."""
        created = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        case = client.get(
            f"/api/v1/applications/{created['created_case_id']}", headers=lawyer_auth
        ).json()
        assert case["business_description"] == INTAKE["business_description"]
        assert case["mark_name"] == INTAKE["mark_name"]

    def test_case_keeps_mark_type_selected_at_intake(self, client, lawyer_auth):
        """Выбранный на первом экране вид знака не должен теряться."""
        created = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        case = client.get(
            f"/api/v1/applications/{created['created_case_id']}", headers=lawyer_auth
        ).json()
        assert case["mark_type"] == "word"

    def test_client_message_is_preserved_in_notes(self, client, lawyer_auth):
        """Текст обращения часто содержит пояснения, которых нет в полях."""
        created = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        case = client.get(
            f"/api/v1/applications/{created['created_case_id']}", headers=lawyer_auth
        ).json()
        assert INTAKE["body_text"] in (case["notes"] or "")

    def test_rejects_intake_without_client(self, client, lawyer_auth):
        payload = {**INTAKE, "new_client": None, "client_id": None}
        response = client.post("/api/v1/inbound/events", json=payload, headers=lawyer_auth)
        assert response.status_code == 400
        assert "клиент" in response.json()["detail"].lower()


@pytest.mark.api
class TestIdempotency:
    """Повтор одного обращения не должен создавать дубликат."""

    def test_repeated_intake_returns_same_event(self, client, lawyer_auth):
        first = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()
        second = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        assert second["is_duplicate"] is True
        assert second["id"] == first["id"]

    def test_repeated_intake_does_not_create_second_case(self, client, lawyer_auth):
        client.post("/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth)
        client.post("/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth)

        events = client.get("/api/v1/inbound/events", headers=lawyer_auth).json()
        assert events["total"] == 1

    def test_explicit_idempotency_key_is_respected(self, client, lawyer_auth):
        payload = {**INTAKE, "idempotency_key": "crm-deal-42"}
        first = client.post(
            "/api/v1/inbound/events", json=payload, headers=lawyer_auth
        ).json()

        # Другое содержимое, но тот же ключ — это то же событие.
        changed = {**payload, "subject": "Совсем другая тема"}
        second = client.post(
            "/api/v1/inbound/events", json=changed, headers=lawyer_auth
        ).json()

        assert second["is_duplicate"] is True
        assert second["id"] == first["id"]

    def test_different_content_creates_new_event(self, client, lawyer_auth):
        client.post("/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth)
        other = {**INTAKE, "subject": "Другое обращение", "mark_name": "КОМЕТА"}
        response = client.post(
            "/api/v1/inbound/events", json=other, headers=lawyer_auth
        ).json()

        assert response["is_duplicate"] is False


@pytest.mark.api
class TestAttachments:
    def test_accepts_valid_document(self, client, lawyer_auth):
        event = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        response = client.post(
            f"/api/v1/inbound/events/{event['id']}/attachments",
            files={"file": ("выписка.pdf", VALID_PDF, "application/pdf")},
            headers=lawyer_auth,
        )
        assert response.status_code == 201
        assert response.json()["accepted"] is True

    def test_rejected_file_is_recorded_not_lost(self, client, lawyer_auth):
        """Юрист должен видеть, что прислал клиент и почему файл не принят."""
        event = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()

        response = client.post(
            f"/api/v1/inbound/events/{event['id']}/attachments",
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
            headers=lawyer_auth,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["accepted"] is False
        assert body["error_message"]

        stored = client.get(
            f"/api/v1/inbound/events/{event['id']}", headers=lawyer_auth
        ).json()
        rejected = [a for a in stored["attachments"] if not a["accepted"]]
        assert rejected
        assert rejected[0]["original_filename"] == "payload.exe"

    def test_attachment_is_linked_to_created_case(self, client, lawyer_auth):
        event = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()
        client.post(
            f"/api/v1/inbound/events/{event['id']}/attachments",
            files={"file": ("док.pdf", VALID_PDF, "application/pdf")},
            headers=lawyer_auth,
        )

        documents = client.get(
            f"/api/v1/applications/{event['created_case_id']}/source-documents",
            headers=lawyer_auth,
        ).json()
        assert documents["total"] == 1

    def test_attachment_records_source_channel(self, client, lawyer_auth):
        """Канал сохраняется: позже сюда встанут crm и email."""
        event = client.post(
            "/api/v1/inbound/events", json=INTAKE, headers=lawyer_auth
        ).json()
        client.post(
            f"/api/v1/inbound/events/{event['id']}/attachments",
            files={"file": ("док.pdf", VALID_PDF, "application/pdf")},
            headers=lawyer_auth,
        )

        documents = client.get(
            f"/api/v1/applications/{event['created_case_id']}/source-documents",
            headers=lawyer_auth,
        ).json()
        assert documents["items"][0]["source_channel"] == "manual_upload"

    def test_attachment_to_missing_event_returns_404(self, client, lawyer_auth):
        response = client.post(
            "/api/v1/inbound/events/999999/attachments",
            files={"file": ("док.pdf", VALID_PDF, "application/pdf")},
            headers=lawyer_auth,
        )
        assert response.status_code == 404
