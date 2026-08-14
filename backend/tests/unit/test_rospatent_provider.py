from __future__ import annotations

import json

import httpx
import pytest

from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.providers.rospatent import RospatentSearchProvider


def _response(request: httpx.Request, status: int, data: object) -> httpx.Response:
    return httpx.Response(status, json=data, request=request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_registered_trademarks_maps_current_flat_shape() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/patsearch/v0.2/search"
        assert request.headers["Authorization"] == "Bearer api-token"
        seen.update(json.loads(request.content))
        return _response(
            request,
            200,
            {
                "total": 1,
                "hits": [
                    {
                        "id": "tm-123",
                        "name": "РЕГИСТР",
                        "trademark_type": "Словесный",
                        "copyright_holder": {"name": 'ООО "Регистр"'},
                        "icgs": [{"class_number": "37"}, {"class_number": 42}],
                        "state": "Действует",
                        "application_number": "2020123456",
                        "certificate_number": "998877",
                        "application_date": "20200102",
                        "registration_date": "20210203",
                        "image": {"url": "https://example.test/tm.png"},
                    }
                ],
            },
        )

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentSearchProvider(
        api_key="api-token",
        trademark_datasets=["ru-trademarks"],
        application_datasets=["ru-trademark-applications"],
        client=client,
    )
    try:
        records = await provider.search_marks(
            SearchQuery(
                mark_text="Регистр",
                classes=[37],
                search_type="exact",
                max_results=10,
            )
        )
    finally:
        await client.aclose()

    assert seen["q"] == '"Регистр"'
    assert seen["datasets"] == ["ru-trademarks"]
    assert seen["filter"]["classification.icgs"]["values"] == ["37"]
    assert len(records) == 1
    record = records[0]
    assert record.record_id == "rospatent:registration:tm-123"
    assert record.external_id == "tm-123"
    assert record.source == "registration"
    assert record.mark_text == "РЕГИСТР"
    assert record.mark_type == "word"
    assert record.owner == 'ООО "Регистр"'
    assert record.classes == [37, 42]
    assert record.status == "registered"
    assert record.filing_date == "2020-01-02"
    assert record.registration_date == "2021-02-03"
    assert record.application_number == "2020123456"
    assert record.registration_number == "998877"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_applications_discovers_datasets_and_maps_nested_hit() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.method == "GET" and request.url.path.endswith("/datasets"):
            return _response(
                request,
                200,
                [
                    {
                        "type": "category",
                        "name_ru": "Товарные знаки",
                        "children": [
                            {"id": "tm-reg", "name_ru": "Регистрации товарных знаков РФ"},
                            {"id": "tm-app", "name_ru": "Заявки на товарные знаки РФ"},
                        ],
                    }
                ],
            )
        body = json.loads(request.content)
        assert body["datasets"] == ["tm-app"]
        return _response(
            request,
            200,
            {
                "hits": {
                    "hits": [
                        {
                            "_id": "app-7",
                            "_source": {
                                "designation": "Регистр плюс",
                                "applicant": [{"name": "Иванов И.И."}],
                                "nice_classes": ["37 - ремонт"],
                                "status": "На экспертизе",
                                "application": {
                                    "number": "2024777000",
                                    "filing_date": "2024-04-05",
                                },
                            },
                        }
                    ]
                }
            },
        )

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentSearchProvider(api_key="api-token", client=client)
    try:
        records = await provider.search_applications(
            SearchQuery(mark_text="Регистр", search_type="fuzzy")
        )
    finally:
        await client.aclose()

    assert calls == [
        "/patsearch/v0.2/datasets",
        "/patsearch/v0.2/search",
    ]
    assert len(records) == 1
    record = records[0]
    assert record.record_id == "rospatent:application:app-7"
    assert record.source == "application"
    assert record.status == "pending"
    assert record.application_number == "2024777000"
    assert record.classes == [37]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_record_uses_document_endpoint_and_returns_none_for_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/missing"):
            return _response(request, 404, {"detail": "not found"})
        assert request.url.path.endswith("/docs/tm-123")
        return _response(
            request,
            200,
            {"id": "tm-123", "name": "РЕГИСТР", "state": "Действует"},
        )

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentSearchProvider(api_key="api-token", client=client)
    try:
        record = await provider.get_record("rospatent:registration:tm-123")
        missing = await provider.get_record("missing")
    finally:
        await client.aclose()

    assert record is not None
    assert record.mark_text == "РЕГИСТР"
    assert missing is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transient_server_error_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _response(request, 503, {"detail": "temporary"})
        return _response(request, 200, {"hits": []})

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentSearchProvider(
        api_key="api-token",
        trademark_datasets=["tm-reg"],
        application_datasets=["tm-app"],
        client=client,
    )
    try:
        assert await provider.search_marks(SearchQuery(mark_text="Регистр")) == []
    finally:
        await client.aclose()

    assert calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generic_trademark_dataset_can_cover_both_record_stages() -> None:
    searched_datasets: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _response(
                request,
                200,
                [{"_id": "all-trademarks", "name_ru": "Товарные знаки РФ"}],
            )
        searched_datasets.append(json.loads(request.content)["datasets"])
        return _response(request, 200, {"hits": []})

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentSearchProvider(api_key="api-token", client=client)
    try:
        await provider.search_marks(SearchQuery(mark_text="Регистр"))
        await provider.search_applications(SearchQuery(mark_text="Регистр"))
    finally:
        await client.aclose()

    assert searched_datasets == [["all-trademarks"], ["all-trademarks"]]
