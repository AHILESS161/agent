from __future__ import annotations

import json
import time

import httpx
import pytest

from app.infrastructure.llm.base import LLMMessage
from app.infrastructure.llm.factory import LLMProviderFactory
from app.infrastructure.llm.gigachat_provider import (
    GigaChatProvider,
    GigaChatStructuredOutputError,
)


def _response(request: httpx.Request, status: int, data: dict) -> httpx.Response:
    return httpx.Response(status, json=data, request=request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_gets_and_reuses_oauth_token() -> None:
    auth_calls = 0
    chat_calls = 0

    def auth_handler(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls
        auth_calls += 1
        assert request.headers["Authorization"] == "Basic auth-key"
        assert request.headers["RqUID"]
        assert request.content == b"scope=GIGACHAT_API_PERS"
        return _response(
            request,
            200,
            {"access_token": "access-token", "expires_at": int(time.time() + 1800)},
        )

    def chat_handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        chat_calls += 1
        assert request.headers["Authorization"] == "Bearer access-token"
        payload = json.loads(request.content)
        assert payload["model"] == "GigaChat-3-Ultra"
        return _response(
            request,
            200,
            {
                "model": "GigaChat-3-Ultra:3.0",
                "choices": [{"message": {"content": "Готово"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    chat_client = httpx.AsyncClient(
        base_url="https://api.giga.chat/v1",
        transport=httpx.MockTransport(chat_handler),
    )
    provider = GigaChatProvider(
        authorization_key="auth-key", client=chat_client, auth_client=auth_client,
        min_request_interval=0,
    )
    try:
        first = await provider.generate([LLMMessage(role="user", content="Тест")])
        second = await provider.generate([LLMMessage(role="user", content="Ещё тест")])
    finally:
        await chat_client.aclose()
        await auth_client.aclose()

    assert first.content == "Готово"
    assert first.model == "GigaChat-3-Ultra:3.0"
    assert first.tokens_input == 3
    assert second.content == "Готово"
    assert auth_calls == 1
    assert chat_calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_structured_generation_uses_json_schema() -> None:
    seen_payload: dict = {}

    def auth_handler(request: httpx.Request) -> httpx.Response:
        return _response(
            request,
            200,
            {"access_token": "token", "expires_at": int(time.time() + 1800)},
        )

    def chat_handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content))
        return _response(
            request,
            200,
            {"choices": [{"message": {"content": '{"risk":"low"}'}}]},
        )

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    chat_client = httpx.AsyncClient(
        base_url="https://api.giga.chat/v1",
        transport=httpx.MockTransport(chat_handler),
    )
    provider = GigaChatProvider(
        authorization_key="auth-key", client=chat_client, auth_client=auth_client,
        min_request_interval=0,
    )
    schema = {"type": "object", "properties": {"risk": {"type": "string"}}}
    try:
        result = await provider.generate_structured(
            [LLMMessage(role="user", content="Оцени риск")], schema
        )
    finally:
        await chat_client.aclose()
        await auth_client.aclose()

    assert result == {"risk": "low"}
    assert seen_payload["response_format"] == {
        "type": "json_schema",
        "schema": schema,
        "strict": True,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_retries_transient_timeout() -> None:
    chat_calls = 0

    def auth_handler(request: httpx.Request) -> httpx.Response:
        return _response(
            request,
            200,
            {"access_token": "token", "expires_at": int(time.time() + 1800)},
        )

    def chat_handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return _response(
            request,
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    chat_client = httpx.AsyncClient(
        base_url="https://api.giga.chat/v1",
        transport=httpx.MockTransport(chat_handler),
    )
    provider = GigaChatProvider(
        authorization_key="auth-key", client=chat_client, auth_client=auth_client,
        min_request_interval=0,
    )
    try:
        result = await provider.generate([LLMMessage(role="user", content="test")])
    finally:
        await chat_client.aclose()
        await auth_client.aclose()

    assert result.content == "ok"
    assert chat_calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_retries_429_using_retry_after(monkeypatch) -> None:
    chat_calls = 0
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "app.infrastructure.llm.gigachat_provider.asyncio.sleep", fake_sleep
    )

    def auth_handler(request: httpx.Request) -> httpx.Response:
        return _response(
            request, 200,
            {"access_token": "token", "expires_at": int(time.time() + 1800)},
        )

    def chat_handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        chat_calls += 1
        if chat_calls == 1:
            return httpx.Response(
                429,
                json={"message": "too many requests"},
                headers={"Retry-After": "7"},
                request=request,
            )
        return _response(
            request, 200,
            {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    chat_client = httpx.AsyncClient(
        base_url="https://api.giga.chat/v1",
        transport=httpx.MockTransport(chat_handler),
    )
    provider = GigaChatProvider(
        authorization_key="auth-key", client=chat_client, auth_client=auth_client,
        min_request_interval=0,
    )
    try:
        result = await provider.generate([LLMMessage(role="user", content="test")])
    finally:
        await chat_client.aclose()
        await auth_client.aclose()

    assert result.content == "ok"
    assert chat_calls == 2
    assert delays and delays[0] >= 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_structured_generation_reports_truncated_json() -> None:
    def auth_handler(request: httpx.Request) -> httpx.Response:
        return _response(
            request, 200,
            {"access_token": "token", "expires_at": int(time.time() + 1800)},
        )

    def chat_handler(request: httpx.Request) -> httpx.Response:
        return _response(
            request, 200,
            {
                "choices": [
                    {
                        "message": {"content": '{"risk":"hi'},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    auth_client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    chat_client = httpx.AsyncClient(
        base_url="https://api.giga.chat/v1",
        transport=httpx.MockTransport(chat_handler),
    )
    provider = GigaChatProvider(
        authorization_key="auth-key", client=chat_client, auth_client=auth_client,
        min_request_interval=0,
    )
    try:
        with pytest.raises(GigaChatStructuredOutputError, match="incomplete"):
            await provider.generate_structured(
                [LLMMessage(role="user", content="test")],
                {"type": "object"},
            )
    finally:
        await chat_client.aclose()
        await auth_client.aclose()


@pytest.mark.unit
def test_factory_creates_gigachat_provider() -> None:
    provider = LLMProviderFactory.create(
        {
            "provider": "gigachat",
            "authorization_key": "auth-key",
            "model": "GigaChat-3-Ultra",
        }
    )
    assert isinstance(provider, GigaChatProvider)
    assert provider.model == "GigaChat-3-Ultra"
