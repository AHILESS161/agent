"""Предзаполнение формы приёма из выписки.

Эндпоинт разбирает выписку в памяти и предлагает значения для формы.
Он ничего не сохраняет и не создаёт: решение и подтверждение остаются
за специалистом, а документ прикрепляется к делу отдельно.
"""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers
from tests.fixtures.egrip_sample import EGRIP_PAGE_1

EGRUL_TEXT = (
    "ВЫПИСКА\n"
    "из Единого государственного реестра юридических лиц\n"
    "1 Полное наименование ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРИМЕР\n"
    "13 ОГРН 1027700132195\n"
    "19 ИНН 7707083893\n"
    "Сведения о регистрирующем органе\n"
)


@pytest.fixture
async def auth(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("prefill@test.ru", UserRole.lawyer)
    return login_headers(client, "prefill@test.ru")


def _prefill(client, auth, filename: str, text: str) -> dict:
    return client.post(
        "/api/v1/intake/prefill-registrant",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
        headers=auth,
    )


@pytest.mark.api
class TestPrefillEgrip:
    def test_egrip_suggests_sole_proprietor(self, client, auth):
        response = _prefill(client, auth, "egrip.txt", EGRIP_PAGE_1)
        assert response.status_code == 200
        body = response.json()

        assert body["document_kind"] == "egrip_extract"
        assert body["client_type"] == "sole_proprietor"

    def test_egrip_prefills_key_fields(self, client, auth):
        body = _prefill(client, auth, "egrip.txt", EGRIP_PAGE_1).json()
        prefill = body["prefill"]

        assert prefill["name"] == "Петров Иван Сергеевич"
        assert prefill["inn"] == "771234567859"
        assert prefill["ogrn"] == "315774600312340"
        # Основной ОКВЭД попадает в описание деятельности для подбора классов.
        assert "47.91.2" in prefill["business_activity"]

    def test_nothing_is_confirmed(self, client, auth):
        body = _prefill(client, auth, "egrip.txt", EGRIP_PAGE_1).json()
        assert "требуют проверки специалистом" in body["notice"]


@pytest.mark.api
class TestPrefillEgrul:
    def test_egrul_suggests_company(self, client, auth):
        body = _prefill(client, auth, "egrul.txt", EGRUL_TEXT).json()
        assert body["document_kind"] == "egrul_extract"
        assert body["client_type"] == "company"
        assert body["prefill"]["inn"] == "7707083893"
        assert body["prefill"]["ogrn"] == "1027700132195"


@pytest.mark.api
class TestPrefillNonRegistry:
    def test_unrecognised_document_warns_not_errors(self, client, auth):
        """Не-выписка — не ошибка: форму заполняют вручную."""
        response = _prefill(
            client, auth, "note.txt", "Просто письмо клиента без реквизитов."
        )
        assert response.status_code == 200
        body = response.json()
        assert body["prefill"] == {}
        assert body["warning"]


@pytest.mark.api
class TestPrefillAuth:
    def test_requires_auth(self, client):
        response = client.post(
            "/api/v1/intake/prefill-registrant",
            files={"file": ("egrip.txt", EGRIP_PAGE_1.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 401
