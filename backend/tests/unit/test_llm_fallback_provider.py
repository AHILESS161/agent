from __future__ import annotations

import pytest

from app.infrastructure.llm.base import LLMMessage, LLMResponse
from app.infrastructure.llm.fallback_provider import FallbackLLMProvider


class StubProvider:
    def __init__(self, model: str, *, error: Exception | None = None) -> None:
        self.model = model
        self.error = error
        self.calls = 0
        self.closed = 0

    async def generate(self, messages, temperature=0.1, max_tokens=4096):
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(
            content=f"ответ {self.model}",
            model=self.model,
            tokens_input=1,
            tokens_output=1,
            latency_ms=1,
        )

    async def generate_structured(self, messages, output_schema, temperature=0.1):
        self.calls += 1
        if self.error:
            raise self.error
        return {"provider": self.model}

    async def aclose(self):
        self.closed += 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_uses_gigachat_after_primary_error() -> None:
    primary = StubProvider("deepseek", error=RuntimeError("temporary failure"))
    fallback = StubProvider("GigaChat-3-Ultra")
    provider = FallbackLLMProvider(primary, fallback)

    response = await provider.generate([LLMMessage(role="user", content="test")])

    assert response.model == "GigaChat-3-Ultra"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert provider.response_used_fallback(response) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_validation_retry_skips_primary() -> None:
    primary = StubProvider("deepseek")
    fallback = StubProvider("GigaChat-3-Ultra")
    provider = FallbackLLMProvider(primary, fallback)

    response = await provider.generate_fallback(
        [LLMMessage(role="user", content="repeat")]
    )

    assert response.model == "GigaChat-3-Ultra"
    assert primary.calls == 0
    assert fallback.calls == 1


@pytest.mark.unit
def test_gigachat_revision_is_recognized_as_fallback() -> None:
    provider = FallbackLLMProvider(
        StubProvider("deepseek"), StubProvider("GigaChat-3-Ultra")
    )
    response = LLMResponse(
        content="ok",
        model="GigaChat-3-Ultra:32.9.23.6",
        tokens_input=1,
        tokens_output=1,
        latency_ms=1,
    )

    assert provider.response_used_fallback(response) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_both_http_clients_are_closed() -> None:
    primary = StubProvider("deepseek")
    fallback = StubProvider("GigaChat-3-Ultra")
    provider = FallbackLLMProvider(primary, fallback)

    await provider.aclose()

    assert primary.closed == 1
    assert fallback.closed == 1
