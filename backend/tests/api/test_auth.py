"""
API tests for authentication endpoints.

Tests the full register → login flow:
- POST /api/v1/auth/register
- POST /api/v1/auth/login (form)
- POST /api/v1/auth/login/json
- GET  /api/v1/auth/me
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

VALID_USER = {
    "email": "test@example.ru",
    "password": "SecurePass123",
    "full_name": "Тестовый Пользователь",
    "role": "client",
}

VALID_USER_2 = {
    "email": "second@example.ru",
    "password": "AnotherPass456",
    "full_name": "Второй Пользователь",
    "role": "client",
}


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

@pytest.mark.api
class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    def test_register_new_user_returns_201(self, client: TestClient):
        """Registering a new valid user should return HTTP 201."""
        response = client.post("/api/v1/auth/register", json=VALID_USER)
        assert response.status_code == 201

    def test_register_returns_user_data(self, client: TestClient):
        """Registration response must include user ID, email, and role."""
        response = client.post("/api/v1/auth/register", json=VALID_USER)
        body = response.json()

        assert "id" in body
        assert body["email"] == VALID_USER["email"]
        assert "role" in body

    def test_register_does_not_return_password(self, client: TestClient):
        """Registered user response must NOT contain the password."""
        response = client.post("/api/v1/auth/register", json=VALID_USER)
        body = response.json()

        assert "password" not in body
        assert "hashed_password" not in body

    def test_register_duplicate_email_returns_409(self, client: TestClient):
        """Registering the same email twice must return 409 Conflict."""
        client.post("/api/v1/auth/register", json=VALID_USER)
        response = client.post("/api/v1/auth/register", json=VALID_USER)
        assert response.status_code == 409

    def test_register_invalid_email_returns_422(self, client: TestClient):
        """Invalid email format must return 422 Unprocessable Entity."""
        payload = {**VALID_USER, "email": "not-an-email"}
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    def test_register_short_password_returns_422(self, client: TestClient):
        """Password shorter than 8 characters must return 422."""
        payload = {**VALID_USER, "password": "short"}
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    def test_register_missing_email_returns_422(self, client: TestClient):
        """Missing email field must return 422."""
        payload = {"password": "SecurePass123", "full_name": "Test"}
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    def test_register_default_role_is_client(self, client: TestClient):
        """User registered without explicit role should default to 'client'."""
        payload = {"email": "norole@test.ru", "password": "Password123"}
        response = client.post("/api/v1/auth/register", json=payload)
        if response.status_code == 201:
            assert response.json()["role"] == "client"


# ---------------------------------------------------------------------------
# Login (form-based) tests
# ---------------------------------------------------------------------------

@pytest.mark.api
class TestLoginForm:
    """Tests for POST /api/v1/auth/login (OAuth2 form)."""

    def test_login_with_valid_credentials_returns_token(self, client: TestClient):
        """Valid credentials should return a JWT access token."""
        client.post("/api/v1/auth/register", json=VALID_USER)

        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": VALID_USER["email"],
                "password": VALID_USER["password"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_token_has_expires_in(self, client: TestClient):
        """Login response must include expires_in field."""
        client.post("/api/v1/auth/register", json=VALID_USER)
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": VALID_USER["email"],
                "password": VALID_USER["password"],
            },
        )
        assert "expires_in" in response.json()

    def test_login_wrong_password_returns_401(self, client: TestClient):
        """Wrong password must return 401 Unauthorized."""
        client.post("/api/v1/auth/register", json=VALID_USER)
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": VALID_USER["email"],
                "password": "WrongPassword!",
            },
        )
        assert response.status_code == 401

    def test_login_unknown_email_returns_401(self, client: TestClient):
        """Login with an unregistered email must return 401."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "nobody@example.com",
                "password": "SomePassword123",
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Login (JSON body) tests
# ---------------------------------------------------------------------------

@pytest.mark.api
class TestLoginJson:
    """Tests for POST /api/v1/auth/login/json."""

    def test_json_login_returns_token(self, client: TestClient):
        """JSON login with valid credentials should return a JWT."""
        client.post("/api/v1/auth/register", json=VALID_USER)

        response = client.post(
            "/api/v1/auth/login/json",
            json={
                "email": VALID_USER["email"],
                "password": VALID_USER["password"],
            },
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_json_login_wrong_credentials_returns_401(self, client: TestClient):
        """Invalid credentials via JSON must return 401."""
        response = client.post(
            "/api/v1/auth/login/json",
            json={"email": "nobody@test.ru", "password": "WrongPass123"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /me tests
# ---------------------------------------------------------------------------

@pytest.mark.api
class TestMe:
    """Tests for GET /api/v1/auth/me."""

    def _register_and_login(self, client: TestClient, user_data: dict = None) -> str:
        """Helper: register, login, return access token."""
        user = user_data or VALID_USER
        client.post("/api/v1/auth/register", json=user)
        login_resp = client.post(
            "/api/v1/auth/login",
            data={"username": user["email"], "password": user["password"]},
        )
        return login_resp.json()["access_token"]

    def test_me_returns_user_profile(self, client: TestClient):
        """Authenticated /me request must return the current user's profile."""
        token = self._register_and_login(client)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == VALID_USER["email"]

    def test_me_without_token_returns_401(self, client: TestClient):
        """Unauthenticated /me request must return 401."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client: TestClient):
        """Invalid/expired token must return 401."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken.abc.xyz"},
        )
        assert response.status_code == 401

    def test_full_register_login_me_flow(self, client: TestClient):
        """Full end-to-end flow: register → login → /me."""
        # 1. Register
        reg_resp = client.post("/api/v1/auth/register", json=VALID_USER_2)
        assert reg_resp.status_code == 201
        user_id = reg_resp.json()["id"]

        # 2. Login
        login_resp = client.post(
            "/api/v1/auth/login",
            data={
                "username": VALID_USER_2["email"],
                "password": VALID_USER_2["password"],
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        # 3. /me
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        me_body = me_resp.json()
        assert me_body["id"] == user_id
        assert me_body["email"] == VALID_USER_2["email"]
        assert me_body["full_name"] == VALID_USER_2["full_name"]
