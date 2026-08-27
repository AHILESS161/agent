"""Удаление дел и клиентов, срочность, разделение работы поверенных."""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def lawyer(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("owner@test.ru", UserRole.lawyer)
    return login_headers(client, "owner@test.ru")


@pytest.fixture
async def colleague(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("colleague@test.ru", UserRole.lawyer)
    return login_headers(client, "colleague@test.ru")


def _client_id(client, headers, name='ООО "Тест"') -> int:
    return client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": name},
        headers=headers,
    ).json()["id"]


def _case(client, headers, mark="ЗВЁЗДОЧКА", client_id=None) -> dict:
    return client.post(
        "/api/v1/applications",
        json={"client_id": client_id or _client_id(client, headers), "mark_name": mark},
        headers=headers,
    ).json()


@pytest.mark.api
class TestClientTextEncoding:
    def test_client_update_repairs_utf8_exposed_as_latin1(self, client, lawyer):
        client_id = _client_id(client, lawyer)
        expected = "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ЦЕНТРПРОЕКТ»"
        damaged_once = expected.encode("utf-8").decode("latin-1")
        damaged = damaged_once.encode("utf-8").decode("latin-1")

        response = client.put(
            f"/api/v1/clients/{client_id}",
            json={"full_name_or_company_name": damaged},
            headers=lawyer,
        )

        assert response.status_code == 200, response.text
        assert response.json()["full_name_or_company_name"] == expected


@pytest.mark.api
class TestPriority:
    """Срочность в работе — не конвенционный приоритет заявки."""

    def test_new_case_is_medium_by_default(self, client, lawyer):
        assert _case(client, lawyer)["priority"] == "medium"

    @pytest.mark.parametrize("value", ["low", "medium", "high"])
    def test_priority_can_be_changed(self, client, lawyer, value):
        case = _case(client, lawyer)
        response = client.put(
            f"/api/v1/applications/{case['id']}",
            json={"priority": value},
            headers=lawyer,
        )
        assert response.status_code == 200
        assert response.json()["priority"] == value

    def test_unknown_priority_is_rejected(self, client, lawyer):
        case = _case(client, lawyer)
        response = client.put(
            f"/api/v1/applications/{case['id']}",
            json={"priority": "срочно"},
            headers=lawyer,
        )
        assert response.status_code == 422

    def test_priority_is_separate_from_convention_priority(self, client, lawyer):
        """priority_claim — дата старшинства заявки, другое поле."""
        case = _case(client, lawyer)
        client.put(
            f"/api/v1/applications/{case['id']}",
            json={"priority": "high", "priority_claim": "01.02.2024"},
            headers=lawyer,
        )
        updated = client.get(
            f"/api/v1/applications/{case['id']}", headers=lawyer
        ).json()
        assert updated["priority"] == "high"
        assert updated["priority_claim"] == "01.02.2024"


@pytest.mark.api
class TestDeleteCase:
    def test_case_can_be_deleted(self, client, lawyer):
        case = _case(client, lawyer)
        assert (
            client.delete(
                f"/api/v1/applications/{case['id']}", headers=lawyer
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/v1/applications/{case['id']}", headers=lawyer
            ).status_code
            == 404
        )

    def test_closed_case_cannot_be_deleted(self, client, lawyer):
        """У закрытого дела есть история — след должен остаться."""
        case = _case(client, lawyer)
        moved = client.post(
            f"/api/v1/applications/{case['id']}/transition",
            json={"new_status": "closed", "reason": "заведено по ошибке"},
            headers=lawyer,
        )
        assert moved.status_code == 200, moved.text

        response = client.delete(
            f"/api/v1/applications/{case['id']}", headers=lawyer
        )
        assert response.status_code == 409
        assert "удалить нельзя" in response.json()["detail"]

    async def test_manager_cannot_delete(self, client, api_user_factory, lawyer):
        case = _case(client, lawyer)
        await api_user_factory("manager-del@test.ru", UserRole.manager)
        manager = login_headers(client, "manager-del@test.ru")

        assert (
            client.delete(
                f"/api/v1/applications/{case['id']}", headers=manager
            ).status_code
            == 403
        )


@pytest.mark.api
class TestDeleteClient:
    def test_client_without_cases_can_be_deleted(self, client, lawyer):
        client_id = _client_id(client, lawyer, 'ООО "Пустой"')
        assert (
            client.delete(f"/api/v1/clients/{client_id}", headers=lawyer).status_code
            == 204
        )

    def test_client_with_cases_is_protected(self, client, lawyer):
        """Иначе вместе с клиентом пропала бы история работы."""
        client_id = _client_id(client, lawyer, 'ООО "С делами"')
        _case(client, lawyer, client_id=client_id)

        response = client.delete(f"/api/v1/clients/{client_id}", headers=lawyer)
        assert response.status_code == 409
        assert "дел" in response.json()["detail"]


@pytest.mark.api
class TestCasesAreSeparatedByOwner:
    """Поверенные ведут свои дела и не мешают друг другу."""

    def _ids(self, client, headers) -> set[int]:
        listing = client.get("/api/v1/applications?page_size=100", headers=headers)
        return {item["id"] for item in listing.json()["items"]}

    def test_colleague_does_not_see_my_cases(self, client, lawyer, colleague):
        mine = _case(client, lawyer, "МОЁ ДЕЛО")
        assert mine["id"] in self._ids(client, lawyer)
        assert mine["id"] not in self._ids(client, colleague)

    def test_new_account_starts_empty(self, client, lawyer, colleague):
        _case(client, lawyer, "МОЁ ДЕЛО")
        assert self._ids(client, colleague) == set()

    def test_each_sees_only_own_cases(self, client, lawyer, colleague):
        mine = _case(client, lawyer, "МОЁ")
        theirs = _case(client, colleague, "ЧУЖОЕ")

        assert self._ids(client, lawyer) == {mine["id"]}
        assert self._ids(client, colleague) == {theirs["id"]}

    async def test_admin_sees_everything(
        self, client, api_user_factory, lawyer, colleague
    ):
        """Администратор должен видеть чужую работу, иначе не поможет."""
        mine = _case(client, lawyer, "МОЁ")
        theirs = _case(client, colleague, "ЧУЖОЕ")

        await api_user_factory("admin-view@test.ru", UserRole.admin)
        admin = login_headers(client, "admin-view@test.ru")

        visible = self._ids(client, admin)
        assert {mine["id"], theirs["id"]} <= visible


@pytest.mark.api
class TestOnlyAdminDeletesOthersCases:
    """Чужая работа не должна исчезать без следа у того, кто её вёл."""

    def test_lawyer_cannot_delete_someone_elses_case(
        self, client, lawyer, colleague
    ):
        case = _case(client, colleague, "ЧУЖОЕ ДЕЛО")
        response = client.delete(
            f"/api/v1/applications/{case['id']}", headers=lawyer
        )
        assert response.status_code == 403
        assert "администратор" in response.json()["detail"]

    def test_owner_deletes_own_case(self, client, lawyer):
        case = _case(client, lawyer, "МОЁ ДЕЛО")
        assert (
            client.delete(
                f"/api/v1/applications/{case['id']}", headers=lawyer
            ).status_code
            == 204
        )

    async def test_admin_deletes_any_case(
        self, client, api_user_factory, colleague
    ):
        case = _case(client, colleague, "ЧУЖОЕ ДЕЛО")

        await api_user_factory("admin-del@test.ru", UserRole.admin)
        admin = login_headers(client, "admin-del@test.ru")

        assert (
            client.delete(
                f"/api/v1/applications/{case['id']}", headers=admin
            ).status_code
            == 204
        )


@pytest.mark.api
class TestDraftVersions:
    """Неудачную версию черновика можно убрать."""

    def _draft(self, client, headers, case_id: int) -> dict:
        return client.post(
            f"/api/v1/applications/{case_id}/draft", headers=headers
        ).json()

    def test_version_can_be_deleted(self, client, lawyer):
        case = _case(client, lawyer)
        draft = self._draft(client, lawyer, case["id"])

        assert (
            client.delete(f"/api/v1/drafts/{draft['id']}", headers=lawyer).status_code
            == 204
        )

        listing = client.get(
            f"/api/v1/applications/{case['id']}/drafts", headers=lawyer
        ).json()
        assert listing["total"] == 0

    def test_exported_version_is_protected(self, client, lawyer):
        """Файл уже ушёл наружу — след о нём должен остаться."""
        case = _case(client, lawyer)
        draft = self._draft(client, lawyer, case["id"])
        client.post(f"/api/v1/drafts/{draft['id']}/approve", headers=lawyer)
        client.get(f"/api/v1/drafts/{draft['id']}/download", headers=lawyer)

        response = client.delete(f"/api/v1/drafts/{draft['id']}", headers=lawyer)
        assert response.status_code == 409

    def test_other_versions_survive(self, client, lawyer):
        case = _case(client, lawyer)
        first = self._draft(client, lawyer, case["id"])
        second = self._draft(client, lawyer, case["id"])

        client.delete(f"/api/v1/drafts/{first['id']}", headers=lawyer)
        listing = client.get(
            f"/api/v1/applications/{case['id']}/drafts", headers=lawyer
        ).json()

        assert [item["id"] for item in listing["items"]] == [second["id"]]

    def test_deletion_requires_auth(self, client, lawyer):
        case = _case(client, lawyer)
        draft = self._draft(client, lawyer, case["id"])
        assert client.delete(f"/api/v1/drafts/{draft['id']}").status_code == 401
