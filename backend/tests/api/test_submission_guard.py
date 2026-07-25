"""Тесты запрета автоматической подачи заявки.

Подача во внешний реестр — юридически значимое и необратимое действие.
Регрессия: шаг подачи выполнялся внутри общего прогона пайплайна
POST /applications/{id}/mvp-run, без отдельного подтверждения. Пока
провайдер был заглушкой, это оставалось незаметным.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def lawyer_auth(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("lawyer-submit@test.ru", UserRole.lawyer)
    return login_headers(client, "lawyer-submit@test.ru")


@pytest.fixture
def case_id(client, lawyer_auth) -> int:
    client_resp = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": 'ООО "Тест"'},
        headers=lawyer_auth,
    )
    app_resp = client.post(
        "/api/v1/applications",
        json={"client_id": client_resp.json()["id"], "mark_name": "ТЕСТ"},
        headers=lawyer_auth,
    )
    return app_resp.json()["id"]


@pytest.mark.api
class TestSubmissionIsBlockedByDefault:
    def test_demo_mode_blocks_submission(self, client, lawyer_auth, case_id, monkeypatch):
        monkeypatch.setattr(settings, "DEMO_MODE", True)
        response = client.post(
            f"/api/v1/applications/{case_id}/submit", headers=lawyer_auth
        )
        assert response.status_code == 403
        assert "демонстрационном режиме" in response.json()["detail"]

    def test_disabled_flag_blocks_submission(
        self, client, lawyer_auth, case_id, monkeypatch
    ):
        monkeypatch.setattr(settings, "DEMO_MODE", False)
        monkeypatch.setattr(settings, "ENABLE_REAL_SUBMISSION", False)
        response = client.post(
            f"/api/v1/applications/{case_id}/submit", headers=lawyer_auth
        )
        assert response.status_code == 403
        assert "ENABLE_REAL_SUBMISSION" in response.json()["detail"]

    def test_confirmation_is_required_even_when_enabled(
        self, client, lawyer_auth, case_id, monkeypatch
    ):
        """Флага недостаточно: нужно явное подтверждение специалистом."""
        monkeypatch.setattr(settings, "DEMO_MODE", False)
        monkeypatch.setattr(settings, "ENABLE_REAL_SUBMISSION", True)
        response = client.post(
            f"/api/v1/applications/{case_id}/submit", headers=lawyer_auth
        )
        assert response.status_code == 400
        assert "confirm=true" in response.json()["detail"]

    def test_submission_requires_authentication(self, client, case_id):
        assert client.post(f"/api/v1/applications/{case_id}/submit").status_code == 401


@pytest.mark.api
class TestDefaultConfiguration:
    def test_demo_mode_is_on_by_default(self):
        assert settings.DEMO_MODE is True

    def test_real_submission_is_off_by_default(self):
        assert settings.ENABLE_REAL_SUBMISSION is False


class TestRegistryProviderIsExplicit:
    def test_unimplemented_provider_fails_loudly(self):
        """Молча подставлять демо-датасет вместо реального провайдера
        нельзя: это выдало бы demo-поиск за полноценный."""
        from app.infrastructure.providers.factory import ProviderFactory

        with pytest.raises(NotImplementedError, match="не реализован"):
            ProviderFactory.create({"provider": "fips"})

    def test_mock_provider_is_available(self):
        from app.infrastructure.providers.factory import ProviderFactory

        assert ProviderFactory.create({"provider": "mock"}) is not None
