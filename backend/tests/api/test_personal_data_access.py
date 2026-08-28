"""Границы доступа к персональным данным и журналу действий."""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def client_owner_headers(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("privacy-owner@test.ru", UserRole.client)
    return login_headers(client, "privacy-owner@test.ru")


@pytest.fixture
async def other_client_headers(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("privacy-other@test.ru", UserRole.client)
    return login_headers(client, "privacy-other@test.ru")


@pytest.mark.api
def test_client_cannot_read_or_add_another_clients_representatives(
    client,
    client_owner_headers,
    other_client_headers,
):
    created = client.post(
        "/api/v1/clients",
        headers=client_owner_headers,
        json={"type": "individual", "full_name_or_company_name": "Иван Иванов"},
    )
    assert created.status_code == 201, created.text
    client_id = created.json()["id"]

    listed = client.get(
        f"/api/v1/clients/{client_id}/representatives",
        headers=other_client_headers,
    )
    added = client.post(
        f"/api/v1/clients/{client_id}/representatives",
        headers=other_client_headers,
        json={"full_name": "Посторонний представитель"},
    )

    assert listed.status_code == 403
    assert added.status_code == 403


@pytest.mark.api
async def test_lawyer_audit_is_limited_to_assigned_cases(
    client,
    api_user_factory,
):
    await api_user_factory("privacy-lawyer-1@test.ru", UserRole.lawyer)
    await api_user_factory("privacy-lawyer-2@test.ru", UserRole.lawyer)
    first_headers = login_headers(client, "privacy-lawyer-1@test.ru")
    second_headers = login_headers(client, "privacy-lawyer-2@test.ru")

    application_ids: list[int] = []
    for headers, name in (
        (first_headers, "Первый заявитель"),
        (second_headers, "Второй заявитель"),
    ):
        created_client = client.post(
            "/api/v1/clients",
            headers=headers,
            json={"type": "company", "full_name_or_company_name": name},
        )
        assert created_client.status_code == 201, created_client.text
        created_application = client.post(
            "/api/v1/applications",
            headers=headers,
            json={
                "client_id": created_client.json()["id"],
                "mark_name": f"ЗНАК {name}",
            },
        )
        assert created_application.status_code == 201, created_application.text
        application_ids.append(created_application.json()["id"])

    response = client.get("/api/v1/audit", headers=first_headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert {item["application_id"] for item in items} == {application_ids[0]}

