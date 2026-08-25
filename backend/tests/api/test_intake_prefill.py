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

EGRUL_WITH_DIRECTOR_TEXT = (
    "ВЫПИСКА\n"
    "из Единого государственного реестра юридических лиц\n"
    "1 Полное наименование ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРИМЕР\n"
    "13 ОГРН 1027700132195\n"
    "19 ИНН 7707083893\n"
    "Сведения о лице, имеющем право без доверенности действовать от имени юридического\n"
    "лица\n"
    "35 ГРН и дата внесения в ЕГРЮЛ сведений о данном лице 1184205019129 27.09.2018\n"
    "36 Фамилия АЛЕКСЕЕНКО\n"
    "37 Имя АНДРЕЙ\n"
    "38 Отчество СЕРГЕЕВИЧ\n"
    "39 ИНН 421406812859\n"
    "40 ГРН и дата внесения в ЕГРЮЛ записи, содержащей указанные сведения 1184205019129 27.09.2018\n"
    "41 Должность ДИРЕКТОР\n"
    "Выписка из ЕГРЮЛ\n"
    "03.06.2020 05:52:20 ОГРН 1027700132195 Страница 2 из 10\n"
    "Сведения об учредителях\n"
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

    def test_egrip_prefills_entrepreneur_as_signatory(self, client, auth):
        prefill = _prefill(client, auth, "egrip.txt", EGRIP_PAGE_1).json()["prefill"]

        assert prefill["signatory_last_name"] == "Петров"
        assert prefill["signatory_first_name"] == "Иван"
        assert prefill["signatory_middle_name"] == "Сергеевич"

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

    def test_egrul_prefills_director_as_signatory(self, client, auth):
        body = _prefill(client, auth, "egrul.txt", EGRUL_WITH_DIRECTOR_TEXT).json()
        prefill = body["prefill"]

        assert prefill["signatory_last_name"] == "Алексеенко"
        assert prefill["signatory_first_name"] == "Андрей"
        assert prefill["signatory_middle_name"] == "Сергеевич"
        assert prefill["signatory_position"] == "ДИРЕКТОР"


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
