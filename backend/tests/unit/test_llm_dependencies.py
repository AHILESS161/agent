from __future__ import annotations

import pytest

import app.api.dependencies as dependencies
from app.infrastructure.llm.factory import LLMProviderFactory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_provider_is_shared_and_closed_once(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.closed = 0

        async def aclose(self) -> None:
            self.closed += 1

    fake = FakeProvider()
    calls = 0

    def create(config):
        nonlocal calls
        calls += 1
        return fake

    await dependencies.close_llm_provider()
    monkeypatch.setattr(LLMProviderFactory, "create", create)

    assert dependencies._get_llm_provider() is fake
    assert dependencies._get_llm_provider() is fake
    assert calls == 1

    await dependencies.close_llm_provider()
    assert fake.closed == 1
    assert dependencies._llm_provider_instance is None

