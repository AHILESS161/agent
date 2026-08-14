from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.infrastructure.providers.base import SearchQuery
from app.infrastructure.providers.factory import ProviderFactory
from app.infrastructure.providers.rospatent_public import (
    RospatentPublicProtocolError,
    RospatentPublicSearchProvider,
)


def _socket_transport(
    results: list[dict[str, Any]],
) -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    namespace_opened = False
    task_sent = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal namespace_opened, task_sent
        assert request.url.path == "/socket.io/"
        sid = request.url.params.get("sid")
        if request.method == "GET" and sid is None:
            return httpx.Response(
                200,
                text='0{"sid":"engine-1","upgrades":[],"pingTimeout":20000}',
                request=request,
            )

        body = request.content.decode("utf-8")
        if request.method == "POST" and body == "40/search,":
            namespace_opened = True
            return httpx.Response(200, text="ok", request=request)
        if request.method == "GET" and namespace_opened and not task_sent:
            return httpx.Response(
                200,
                text='40/search,{"sid":"namespace-1"}',
                request=request,
            )
        if request.method == "POST" and body.startswith("42/search,"):
            event = json.loads(body[len("42/search,") :])
            assert event[0] == "send_task"
            tasks.append(event[1])
            task_sent = True
            return httpx.Response(200, text="ok", request=request)
        if request.method == "GET" and task_sent:
            payload = {
                "totalResult": len(results),
                "totalPages": 1,
                "data": results,
            }
            packet = "42/search," + json.dumps(
                ["send_results", payload], ensure_ascii=False, separators=(",", ":")
            )
            return httpx.Response(200, text=packet, request=request)
        if request.method == "POST" and body == "41/search,":
            return httpx.Response(200, text="ok", request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url} {body}")

    return httpx.MockTransport(handler), tasks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_marks_maps_public_result_and_exact_filters() -> None:
    transport, tasks = _socket_transport(
        [
            {
                "object_uid": "uid-registration",
                "trademarkKind": 1,
                "tmk_kind": "Регистрация",
                "mark_description_text": "РЕГИСТР",
                "holders": "ООО «Регистр»",
                "goodClasses": ["09", "35", "42"],
                "status_code": 2,
                "appl_number": "2020123456",
                "appl_date": "2020-01-02T00:00:00",
                "reg_number": "998877",
                "reg_date": "2021-02-03T00:00:00",
                "files": [{"file_url": "https://example.test/mark.png"}],
            },
            {
                "object_uid": "uid-application",
                "trademarkKind": 2,
                "tmk_kind": "Заявка",
                "mark_description_text": "РЕГИСТР ПЛЮС",
                "goodClasses": ["42"],
                "appl_number": "2024777000",
            },
        ]
    )
    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/",
        transport=transport,
    )
    provider = RospatentPublicSearchProvider(
        client=client,
        min_interval=0,
    )
    try:
        records = await provider.search_marks(
            SearchQuery(
                mark_text="Регистр",
                classes=[42],
                search_type="exact",
                max_results=10,
            )
        )
    finally:
        await client.aclose()

    assert len(records) == 1
    record = records[0]
    assert record.record_id == "rospatent-public:registration:uid-registration"
    assert record.mark_text == "РЕГИСТР"
    assert record.mark_type == "word"
    assert record.owner == "ООО «Регистр»"
    assert record.classes == [9, 35, 42]
    assert record.status == "registered"
    assert record.filing_date == "2020-01-02"
    assert record.registration_date == "2021-02-03"
    assert record.image_url == "https://example.test/mark.png"

    task = tasks[0]
    parameters = task["data"]["query"]["data"]["parameters"]
    assert parameters["search_kind_id"] == "match"
    assert parameters["data_sources"] == [
        "trademarks",
        "known_trademarks",
        "international_trademarks",
    ]
    assert task["data"]["filter"] == {"goods_classes": ["42"]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_applications_uses_application_filter() -> None:
    transport, tasks = _socket_transport(
        [
            {
                "object_uid": "uid-application",
                "trademarkKind": "2",
                "tmk_kind": "Заявка",
                "mark_description_text": "РЕГИСТР ПЛЮС",
                "holders": "Иванов И.И.",
                "goodClasses": ["37"],
                "appl_number": "2024777000",
                "appl_date": "2024-04-05",
            }
        ]
    )
    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/",
        transport=transport,
    )
    provider = RospatentPublicSearchProvider(client=client, min_interval=0)
    try:
        records = await provider.search_applications(
            SearchQuery(mark_text="Регистр", search_type="fuzzy")
        )
    finally:
        await client.aclose()

    assert len(records) == 1
    assert records[0].source == "application"
    assert records[0].status == "pending"
    assert records[0].application_number == "2024777000"
    assert tasks[0]["data"]["filter"] == {"trademark_type": 2}
    parameters = tasks[0]["data"]["query"]["data"]["parameters"]
    assert parameters["search_kind_id"] == "fuzzy"


@pytest.mark.unit
def test_factory_creates_public_provider_without_api_key() -> None:
    provider = ProviderFactory.create(
        {
            "provider": "rospatent_public",
            "public_min_interval": 0,
        }
    )
    assert isinstance(provider, RospatentPublicSearchProvider)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_engine_handshake_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-a-handshake", request=request)

    client = httpx.AsyncClient(
        base_url="https://searchplatform.rospatent.gov.ru/",
        transport=httpx.MockTransport(handler),
    )
    provider = RospatentPublicSearchProvider(client=client, min_interval=0)
    try:
        with pytest.raises(RospatentPublicProtocolError):
            await provider.search_marks(SearchQuery(mark_text="Регистр"))
    finally:
        await client.aclose()
