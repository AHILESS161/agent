"""Управление пользователями и назначение дел.

Учётные записи заводит только администратор: эндпоинт принимает роль,
и в открытом виде любой назначил бы себе права администратора.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def admin(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("root@test.ru", UserRole.admin)
    return login_headers(client, "root@test.ru")


@pytest.fixture
async def lawyer(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("worker@test.ru", UserRole.lawyer)
    return login_headers(client, "worker@test.ru")


def _create(client, admin, email="new@test.ru", role="lawyer"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strongpass123",
            "full_name": "Новый Сотрудник",
            "role": role,
        },
        headers=admin,
    )


@pytest.mark.api
class TestCreateUser:
    def test_admin_creates_user(self, client, admin):
        response = _create(client, admin)
        assert response.status_code == 201
        assert response.json()["role"] == "lawyer"

    def test_lawyer_cannot_create_user(self, client, lawyer):
        """Иначе любой назначил бы себе права администратора."""
        assert _create(client, lawyer).status_code == 403

    def test_new_user_can_log_in(self, client, admin):
        _create(client, admin, email="fresh@test.ru")
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "fresh@test.ru", "password": "strongpass123"},
        )
        assert response.status_code == 200


@pytest.mark.api
class TestRoles:
    def test_admin_changes_role(self, client, admin):
        user = _create(client, admin, email="promote@test.ru").json()

        response = client.put(
            f"/api/v1/users/{user['id']}", json={"role": "admin"}, headers=admin
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_lawyer_cannot_change_roles(self, client, admin, lawyer):
        user = _create(client, admin, email="target@test.ru").json()
        response = client.put(
            f"/api/v1/users/{user['id']}", json={"role": "admin"}, headers=lawyer
        )
        assert response.status_code == 403


@pytest.mark.api
class TestAccess:
    def test_admin_disables_access(self, client, admin):
        """Доступ отключается, а не стирается: пользователь связан
        с делами и журналом, и удаление порвало бы историю."""
        user = _create(client, admin, email="off@test.ru").json()

        assert (
            client.delete(f"/api/v1/users/{user['id']}", headers=admin).status_code
            == 204
        )
        assert (
            client.get(f"/api/v1/users/{user['id']}", headers=admin).json()["is_active"]
            is False
        )

    def test_disabled_user_cannot_log_in(self, client, admin):
        _create(client, admin, email="blocked@test.ru")
        user = client.get("/api/v1/users?page=1&page_size=100", headers=admin).json()
        target = next(u for u in user["items"] if u["email"] == "blocked@test.ru")
        client.delete(f"/api/v1/users/{target['id']}", headers=admin)

        response = client.post(
            "/api/v1/auth/login",
            data={"username": "blocked@test.ru", "password": "strongpass123"},
        )
        # Учётная запись существует, но доступ закрыт — 403 по смыслу.
        assert response.status_code == 403

    def test_access_can_be_restored(self, client, admin):
        user = _create(client, admin, email="back@test.ru").json()
        client.delete(f"/api/v1/users/{user['id']}", headers=admin)

        restored = client.put(
            f"/api/v1/users/{user['id']}", json={"is_active": True}, headers=admin
        )
        assert restored.json()["is_active"] is True

    def test_admin_cannot_disable_self(self, client, admin):
        """Иначе администратор заблокировал бы сам себя."""
        me = client.get("/api/v1/auth/me", headers=admin).json()
        response = client.delete(f"/api/v1/users/{me['id']}", headers=admin)
        assert response.status_code == 400


@pytest.mark.api
class TestAssignment:
    def _case(self, client, headers) -> dict:
        client_id = client.post(
            "/api/v1/clients",
            json={"type": "company", "full_name_or_company_name": 'ООО "Тест"'},
            headers=headers,
        ).json()["id"]
        return client.post(
            "/api/v1/applications",
            json={"client_id": client_id, "mark_name": "ЗВЁЗДОЧКА"},
            headers=headers,
        ).json()

    def test_case_can_be_assigned(self, client, admin):
        case = self._case(client, admin)
        worker = _create(client, admin, email="assignee@test.ru").json()

        response = client.put(
            f"/api/v1/applications/{case['id']}",
            json={"assigned_lawyer_id": worker["id"]},
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["assigned_lawyer_id"] == worker["id"]

    def test_assigned_case_becomes_visible(self, client, admin):
        """Назначение определяет и видимость: исполнитель должен
        увидеть дело в своём списке."""
        case = self._case(client, admin)
        _create(client, admin, email="sees@test.ru")
        listing = client.get("/api/v1/users?page=1&page_size=100", headers=admin).json()
        worker = next(u for u in listing["items"] if u["email"] == "sees@test.ru")

        worker_headers = login_headers(client, "sees@test.ru", "strongpass123")
        before = client.get("/api/v1/applications", headers=worker_headers).json()
        assert case["id"] not in {item["id"] for item in before["items"]}

        client.put(
            f"/api/v1/applications/{case['id']}",
            json={"assigned_lawyer_id": worker["id"]},
            headers=admin,
        )

        after = client.get("/api/v1/applications", headers=worker_headers).json()
        assert case["id"] in {item["id"] for item in after["items"]}
