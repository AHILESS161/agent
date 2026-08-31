"""Управление классами МКТУ специалистом.

Предложенный системой класс — это предложение: пока специалист его
не подтвердил, он не попадает в заявление. Подбор по описанию
деятельности покрывает не всё, поэтому класс можно добавить вручную
и убрать лишний.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


class _NarrowingProvider:
    async def generate_structured(self, **_kwargs):
        return {
            "selected_indices": [1, 2],
            "rationale": "Эти позиции прямо соответствуют описанию деятельности.",
            "assumptions": [],
        }


@pytest.fixture
async def lawyer(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("classes@test.ru", UserRole.lawyer)
    return login_headers(client, "classes@test.ru")


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


@pytest.mark.api
class TestManualClass:
    def test_specialist_can_add_a_class(self, client, lawyer, case):
        response = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25, "class_description": "Одежда; обувь"},
            headers=lawyer,
        )
        assert response.status_code == 201
        assert response.json()["class_number"] == 25

    def test_manual_class_is_confirmed_immediately(self, client, lawyer, case):
        """Решение специалиста не нуждается в подтверждении системой."""
        response = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        )
        assert response.json()["approved"] is True

    def test_manual_class_without_custom_text_uses_full_official_list(
        self, client, lawyer, case
    ):
        response = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        )
        description = response.json()["class_description"]
        assert len(description) > 2_000
        assert ";" in description

    def test_duplicate_class_is_rejected(self, client, lawyer, case):
        client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        )
        again = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        )
        assert again.status_code == 409

    @pytest.mark.parametrize("number", [0, 46, -1])
    def test_class_number_must_be_valid(self, client, lawyer, case, number):
        """МКТУ содержит классы с 1 по 45."""
        response = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": number},
            headers=lawyer,
        )
        assert response.status_code == 422

    def test_class_can_be_removed(self, client, lawyer, case):
        created = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        ).json()

        removed = client.delete(
            f"/api/v1/applications/{case}/classes/{created['id']}", headers=lawyer
        )
        assert removed.status_code == 204

        listing = client.get(
            f"/api/v1/applications/{case}/classes", headers=lawyer
        ).json()
        assert listing["suggestions"] == []


@pytest.mark.api
class TestApproval:
    def test_class_can_be_approved_and_rejected(self, client, lawyer, case):
        created = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=lawyer,
        ).json()

        rejected = client.put(
            f"/api/v1/applications/{case}/classes/{created['id']}/approve",
            json={"suggestion_id": created["id"], "approved": False},
            headers=lawyer,
        )
        assert rejected.json()["approved"] is False

        approved = client.put(
            f"/api/v1/applications/{case}/classes/{created['id']}/approve",
            json={
                "suggestion_id": created["id"],
                "approved": True,
                "class_description": "ремонт и обслуживание компьютеров",
            },
            headers=lawyer,
        )
        assert approved.json()["approved"] is True
        assert approved.json()["class_description"] == "ремонт и обслуживание компьютеров"


@pytest.mark.api
class TestModelNarrowing:
    def test_preview_does_not_change_list_and_apply_uses_official_items(
        self, client, lawyer, case, monkeypatch
    ):
        from app.api.v1.endpoints import applications

        client.put(
            f"/api/v1/applications/{case}",
            json={
                "business_description": "Устанавливаем и ремонтируем компьютеры",
                "goods_services_raw": "установка и ремонт компьютеров",
            },
            headers=lawyer,
        )
        created = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 37},
            headers=lawyer,
        ).json()
        original = created["class_description"]
        monkeypatch.setattr(applications, "_get_llm_provider", lambda: _NarrowingProvider())

        preview_response = client.post(
            f"/api/v1/applications/{case}/classes/{created['id']}/narrow",
            json={},
            headers=lawyer,
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["selected_count"] == 2
        assert preview["source_count"] > preview["selected_count"]

        still_original = client.get(
            f"/api/v1/applications/{case}/classes", headers=lawyer
        ).json()["suggestions"][0]["class_description"]
        assert still_original == original

        applied = client.post(
            f"/api/v1/applications/{case}/classes/{created['id']}/narrow/apply",
            json={"selected_items": preview["selected_items"]},
            headers=lawyer,
        )
        assert applied.status_code == 200
        assert applied.json()["class_description"] == preview["proposed_description"]

    def test_apply_rejects_text_not_found_in_official_catalogue(
        self, client, lawyer, case
    ):
        created = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 37},
            headers=lawyer,
        ).json()
        response = client.post(
            f"/api/v1/applications/{case}/classes/{created['id']}/narrow/apply",
            json={"selected_items": ["любые хорошие услуги"]},
            headers=lawyer,
        )
        assert response.status_code == 422


@pytest.mark.api
class TestAccess:
    async def test_manager_cannot_add_classes(
        self, client, api_user_factory, lawyer, case
    ):
        """Перечень классов определяет специалист."""
        await api_user_factory("manager-classes@test.ru", UserRole.manager)
        manager = login_headers(client, "manager-classes@test.ru")

        response = client.post(
            f"/api/v1/applications/{case}/classes",
            json={"class_number": 25},
            headers=manager,
        )
        assert response.status_code == 403

    def test_anonymous_cannot_add_classes(self, client, case):
        assert (
            client.post(
                f"/api/v1/applications/{case}/classes", json={"class_number": 25}
            ).status_code
            == 401
        )
