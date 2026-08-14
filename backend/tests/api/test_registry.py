from __future__ import annotations

import pytest

from app.api.dependencies import get_registry_provider
from app.infrastructure.database.models import UserRole
from app.infrastructure.providers.base import RegistryRecord
from tests.conftest import login_headers


class FakeRegistryProvider:
    async def search_marks(self, query):
        assert query.mark_text == "Регистр"
        return [
            RegistryRecord(
                record_id="rospatent:registration:1",
                external_id="1",
                source="registration",
                mark_text="РЕГИСТР",
                mark_type="word",
                owner='ООО "Регистр"',
                classes=[37],
                status="registered",
                filing_date="2020-01-01",
                registration_date="2021-01-01",
            )
        ]

    async def search_applications(self, query):
        return [
            RegistryRecord(
                record_id="rospatent:application:2",
                external_id="2",
                source="application",
                mark_text="РЕГИСТР ПЛЮС",
                mark_type="word",
                owner="Иванов И.И.",
                classes=[37],
                status="pending",
                filing_date="2024-01-01",
                registration_date=None,
            )
        ]

    async def list_datasets(self):
        return [{"id": "tm-reg", "name_ru": "Товарные знаки РФ"}]

    async def get_record(self, record_id):
        if record_id == "missing":
            return None
        return (await self.search_marks(type("Query", (), {"mark_text": "Регистр"})()))[0]


@pytest.fixture
async def registry_auth(client, api_user_factory):
    await api_user_factory("registry-lawyer@test.ru", UserRole.lawyer)
    return login_headers(client, "registry-lawyer@test.ru")


@pytest.mark.api
def test_registry_search_returns_registrations_and_applications(
    client, registry_auth, monkeypatch
):
    monkeypatch.setattr("app.api.v1.endpoints.registry.settings.FIPS_PROVIDER", "fips")
    client.app.dependency_overrides[get_registry_provider] = FakeRegistryProvider

    response = client.post(
        "/api/v1/registry/search",
        json={"query": "Регистр", "classes": [37], "source": "both"},
        headers=registry_auth,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fips"
    assert body["total"] == 2
    assert {record["source"] for record in body["records"]} == {
        "registration",
        "application",
    }


@pytest.mark.api
def test_registry_both_sources_share_a_small_global_limit(
    client, registry_auth
):
    class ManyRegistrationsProvider(FakeRegistryProvider):
        async def search_marks(self, query):
            first = (await super().search_marks(query))[0]
            return [
                first,
                first.model_copy(
                    update={
                        "record_id": "rospatent:registration:3",
                        "external_id": "3",
                    }
                ),
            ]

    client.app.dependency_overrides[get_registry_provider] = ManyRegistrationsProvider
    response = client.post(
        "/api/v1/registry/search",
        json={
            "query": "Регистр",
            "classes": [37],
            "source": "both",
            "max_results": 2,
        },
        headers=registry_auth,
    )

    assert response.status_code == 200
    assert [record["source"] for record in response.json()["records"]] == [
        "registration",
        "application",
    ]


@pytest.mark.api
def test_registry_datasets_and_record_require_auth(client, registry_auth):
    client.app.dependency_overrides[get_registry_provider] = FakeRegistryProvider

    assert client.get("/api/v1/registry/datasets").status_code == 401
    datasets = client.get("/api/v1/registry/datasets", headers=registry_auth)
    assert datasets.status_code == 200
    assert datasets.json()["datasets"][0]["id"] == "tm-reg"

    missing = client.get("/api/v1/registry/records/missing", headers=registry_auth)
    assert missing.status_code == 404
