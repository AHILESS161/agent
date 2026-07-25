"""Тесты безопасности авторизации.

Регрессия: эндпоинт /auth/register был открыт для всех и принимал поле
``role``. Любой, у кого есть адрес сервиса, мог создать себе учётную
запись администратора. Для системы, выставляемой наружу по временной
ссылке, это блокирующая проблема.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers

NEW_ADMIN = {
    "email": "attacker@example.com",
    "password": "supersecret123",
    "full_name": "Посторонний",
    "role": "admin",
}


@pytest.mark.api
class TestRegistrationIsClosed:
    def test_anonymous_cannot_register(self, client):
        response = client.post("/api/v1/auth/register", json=NEW_ADMIN)
        assert response.status_code == 401

    def test_anonymous_cannot_self_assign_admin_role(self, client):
        """Ключевая проверка: самоназначение роли admin невозможно."""
        client.post("/api/v1/auth/register", json=NEW_ADMIN)
        login = client.post(
            "/api/v1/auth/login/json",
            json={"email": NEW_ADMIN["email"], "password": NEW_ADMIN["password"]},
        )
        assert login.status_code == 401, "учётная запись не должна была создаться"

    async def test_specialist_cannot_register_users(self, client, api_user_factory):
        await api_user_factory("lawyer-sec@test.ru", UserRole.lawyer)
        headers = login_headers(client, "lawyer-sec@test.ru")

        response = client.post("/api/v1/auth/register", json=NEW_ADMIN, headers=headers)
        assert response.status_code == 403

    async def test_admin_can_register_users(self, client, api_user_factory):
        await api_user_factory("admin-sec@test.ru", UserRole.admin)
        headers = login_headers(client, "admin-sec@test.ru")

        response = client.post("/api/v1/auth/register", json=NEW_ADMIN, headers=headers)
        assert response.status_code == 201
        assert response.json()["email"] == NEW_ADMIN["email"]


@pytest.mark.api
class TestLogin:
    async def test_wrong_password_is_rejected(self, client, api_user_factory):
        await api_user_factory("user-login@test.ru", UserRole.lawyer)
        response = client.post(
            "/api/v1/auth/login/json",
            json={"email": "user-login@test.ru", "password": "неверный"},
        )
        assert response.status_code == 401

    async def test_correct_password_returns_token(self, client, api_user_factory):
        await api_user_factory("user-ok@test.ru", UserRole.lawyer)
        response = client.post(
            "/api/v1/auth/login/json",
            json={"email": "user-ok@test.ru", "password": "test12345"},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_unknown_email_is_rejected(self, client):
        response = client.post(
            "/api/v1/auth/login/json",
            json={"email": "nobody@test.ru", "password": "test12345"},
        )
        assert response.status_code == 401

    async def test_token_grants_access_to_protected_route(self, client, api_user_factory):
        await api_user_factory("user-me@test.ru", UserRole.lawyer)
        headers = login_headers(client, "user-me@test.ru")

        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["email"] == "user-me@test.ru"

    def test_protected_route_requires_token(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401
