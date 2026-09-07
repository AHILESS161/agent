from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.infrastructure.database.models import PendingSignup, UserRole
from app.api.v1.endpoints import signup


@pytest.fixture
def mail(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", True)
    for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.setattr(settings, key, "synthetic@example.com")
    sender = AsyncMock()
    monkeypatch.setattr(signup, "send_confirmation_email", sender)
    return sender


def request_link(client, mail, email="new@example.com"):
    response = client.post("/api/v1/auth/signup/request", json={"email": email})
    assert response.status_code == 202, response.text
    return mail.call_args.args[1]


def confirm(client, token, **extra):
    return client.post("/api/v1/auth/signup/confirm", json={"token": token,
        "password": "strong-test-password", "full_name": "Новый клиент", **extra})


def test_signup_creates_only_verified_client_and_token_is_single_use(client, mail):
    token = request_link(client, mail, "NEW@example.com")
    assert client.post("/api/v1/auth/login/json", json={"email": "new@example.com",
        "password": "strong-test-password"}).status_code == 401
    assert confirm(client, token).status_code == 201
    assert confirm(client, token).status_code == 400
    logged = client.post("/api/v1/auth/login/json", json={"email": "NEW@example.com",
        "password": "strong-test-password"})
    assert logged.status_code == 200, logged.text
    profile = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + logged.json()["access_token"]})
    assert profile.json()["role"] == "client"
    assert profile.json()["email"] == "new@example.com"


@pytest.mark.parametrize("role", ["admin", "lawyer", "manager"])
def test_public_signup_rejects_privileged_role_in_both_steps(client, mail, role):
    assert client.post("/api/v1/auth/signup/request", json={"email": "new@example.com", "role": role}).status_code == 422
    token = request_link(client, mail)
    assert confirm(client, token, role=role).status_code == 422
    assert confirm(client, token).status_code == 201


@pytest.mark.asyncio
async def test_expired_token_cannot_create_user(client, mail, async_engine):
    token = request_link(client, mail)
    async with async_sessionmaker(async_engine)() as session:
        await session.execute(update(PendingSignup).values(expires_at=datetime.now(timezone.utc) - timedelta(hours=2)))
        await session.commit()
    assert confirm(client, token).status_code == 400


def test_new_letter_does_not_invalidate_previous_letter_but_confirmation_consumes_all(client, mail):
    first = request_link(client, mail)
    second = request_link(client, mail)
    assert first != second
    assert confirm(client, first).status_code == 201
    assert confirm(client, second).status_code == 400


@pytest.mark.asyncio
async def test_existing_privileged_account_is_not_modified(client, mail, api_user_factory):
    await api_user_factory("owner@example.com", UserRole.admin)
    result = client.post("/api/v1/auth/signup/request", json={"email": "OWNER@example.com"})
    assert result.status_code == 202
    assert result.json()["message"] == signup.GENERIC_MESSAGE
    mail.assert_not_called()


@pytest.mark.asyncio
async def test_delivery_failure_leaves_no_valid_token_and_still_counts_attempt(client, mail, monkeypatch, async_engine):
    monkeypatch.setattr(settings, "SIGNUP_DAILY_EMAIL_LIMIT", 1)
    mail.side_effect = RuntimeError("SMTP credential must never reach the response")
    result = client.post("/api/v1/auth/signup/request", json={"email": "new@example.com"})
    assert result.status_code == 503
    assert "credential" not in result.text
    assert client.post("/api/v1/auth/signup/request", json={"email": "new@example.com"}).status_code == 429
    async with async_sessionmaker(async_engine)() as session:
        assert await session.scalar(select(PendingSignup.token_hash)) is None


def test_signup_disabled_without_configured_mail(client, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert client.get("/api/v1/auth/signup/config").json() == {"enabled": False}
    assert client.post("/api/v1/auth/signup/request", json={"email": "new@example.com"}).status_code == 503
