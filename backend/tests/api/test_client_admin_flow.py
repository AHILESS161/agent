"""Клиентские заявки в административном контуре и доступ к расчёту пошлин."""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


def _create_case(api_client, headers: dict[str, str], mark: str = "КЛИЕНТСКИЙ ЗНАК") -> dict:
    applicant = api_client.post(
        "/api/v1/clients",
        json={"type": "individual", "full_name_or_company_name": "Клиент продукта"},
        headers=headers,
    )
    assert applicant.status_code == 201, applicant.text
    application = api_client.post(
        "/api/v1/applications",
        json={"client_id": applicant.json()["id"], "mark_name": mark, "mark_type": "word"},
        headers=headers,
    )
    assert application.status_code == 201, application.text
    return application.json()


@pytest.mark.api
class TestClientApplicationRouting:
    async def test_common_classification_uses_precise_local_catalog(
        self, client, api_user_factory
    ):
        await api_user_factory("customer-repair@test.ru", UserRole.client)
        customer = login_headers(client, "customer-repair@test.ru")
        application = _create_case(client, customer, "МАСТЕР")
        updated = client.put(
            f"/api/v1/applications/{application['id']}",
            json={
                "business_description": "Ремонт бытовой техники",
                "goods_services_raw": "Ремонт бытовой техники",
            },
            headers=customer,
        )
        assert updated.status_code == 200, updated.text

        response = client.post(
            f"/api/v1/applications/{application['id']}/nice-classes/suggest",
            headers=customer,
        )

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "catalog"
        assert [
            item["class_number"] for item in response.json()["suggestions"]
        ] == [37]

    async def test_explicit_sales_add_trade_services_class(
        self, client, api_user_factory
    ):
        await api_user_factory("customer-clothes@test.ru", UserRole.client)
        customer = login_headers(client, "customer-clothes@test.ru")
        application = _create_case(client, customer, "ОДЕЖДА")
        client.put(
            f"/api/v1/applications/{application['id']}",
            json={
                "business_description": "Производство одежды и продажа через интернет-магазин",
                "goods_services_raw": "Производство одежды и продажа через интернет-магазин",
            },
            headers=customer,
        )

        response = client.post(
            f"/api/v1/applications/{application['id']}/nice-classes/suggest",
            headers=customer,
        )

        assert response.status_code == 201, response.text
        assert {
            item["class_number"] for item in response.json()["suggestions"]
        } == {25, 35}

    async def test_client_can_delete_own_draft(self, client, api_user_factory):
        await api_user_factory("customer-delete@test.ru", UserRole.client)
        customer = login_headers(client, "customer-delete@test.ru")
        application = _create_case(client, customer, "УДАЛЯЕМЫЙ ЧЕРНОВИК")

        deleted = client.delete(
            f"/api/v1/applications/{application['id']}", headers=customer
        )

        assert deleted.status_code == 204, deleted.text
        assert (
            client.get(
                f"/api/v1/applications/{application['id']}", headers=customer
            ).status_code
            == 404
        )

    async def test_client_cannot_delete_another_clients_draft(
        self, client, api_user_factory
    ):
        await api_user_factory("customer-owner@test.ru", UserRole.client)
        await api_user_factory("customer-stranger@test.ru", UserRole.client)
        owner = login_headers(client, "customer-owner@test.ru")
        stranger = login_headers(client, "customer-stranger@test.ru")
        application = _create_case(client, owner, "ЧУЖОЙ ЧЕРНОВИК")

        denied = client.delete(
            f"/api/v1/applications/{application['id']}", headers=stranger
        )

        assert denied.status_code == 403

    async def test_client_application_is_visible_to_admin(self, client, api_user_factory):
        await api_user_factory("customer-flow@test.ru", UserRole.client)
        await api_user_factory("admin-flow@test.ru", UserRole.admin)
        customer = login_headers(client, "customer-flow@test.ru")
        admin = login_headers(client, "admin-flow@test.ru")

        application = _create_case(client, customer)
        listing = client.get("/api/v1/applications?page_size=100", headers=admin)

        assert listing.status_code == 200
        assert application["id"] in {item["id"] for item in listing.json()["items"]}

    async def test_admin_can_open_client_application_and_calculate_fees(self, client, api_user_factory):
        await api_user_factory("customer-fees@test.ru", UserRole.client)
        await api_user_factory("admin-fees@test.ru", UserRole.admin)
        customer = login_headers(client, "customer-fees@test.ru")
        admin = login_headers(client, "admin-fees@test.ru")
        application = _create_case(client, customer, "ПОШЛИНА")

        assert client.get(f"/api/v1/applications/{application['id']}", headers=admin).status_code == 200
        fees = client.get(f"/api/v1/applications/{application['id']}/fees", headers=admin)
        assert fees.status_code == 200
        assert "payments" in fees.json()

    async def test_assigned_lawyer_can_calculate_client_application_fees(self, client, api_user_factory):
        await api_user_factory("customer-lawyer@test.ru", UserRole.client)
        await api_user_factory("admin-assign@test.ru", UserRole.admin)
        lawyer_user = await api_user_factory("assigned-lawyer@test.ru", UserRole.lawyer)
        customer = login_headers(client, "customer-lawyer@test.ru")
        admin = login_headers(client, "admin-assign@test.ru")
        lawyer = login_headers(client, "assigned-lawyer@test.ru")
        application = _create_case(client, customer, "ДЕЛО ЮРИСТА")

        assigned = client.put(
            f"/api/v1/applications/{application['id']}",
            json={"assigned_lawyer_id": lawyer_user.id},
            headers=admin,
        )
        assert assigned.status_code == 200, assigned.text

        fees = client.get(f"/api/v1/applications/{application['id']}/fees", headers=lawyer)
        assert fees.status_code == 200
        assert "payments" in fees.json()
