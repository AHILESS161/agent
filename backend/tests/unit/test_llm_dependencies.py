from __future__ import annotations

import pytest

import app.api.dependencies as dependencies
from app.core.config import settings
from app.infrastructure.llm.factory import LLMProviderFactory
from app.infrastructure.llm.fallback_provider import FallbackLLMProvider


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
    monkeypatch.setattr(settings, "LLM_FALLBACK_ENABLED", False)

    assert dependencies._get_llm_provider() is fake
    assert dependencies._get_llm_provider() is fake
    assert calls == 1

    await dependencies.close_llm_provider()
    assert fake.closed == 1
    assert dependencies._llm_provider_instance is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gigachat_is_attached_as_fallback_when_key_exists(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, model: str) -> None:
            self.model = model

        async def aclose(self) -> None:
            return None

    created: list[dict] = []

    def create(config):
        created.append(config)
        return FakeProvider(config.get("model") or config["provider"])

    await dependencies.close_llm_provider()
    monkeypatch.setattr(LLMProviderFactory, "create", create)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "routerai")
    monkeypatch.setattr(settings, "LLM_MODEL", "deepseek/test")
    monkeypatch.setattr(settings, "GIGACHAT_AUTHORIZATION_KEY", "configured")
    monkeypatch.setattr(settings, "LLM_FALLBACK_ENABLED", True)

    provider = dependencies._get_llm_provider()

    assert isinstance(provider, FallbackLLMProvider)
    assert [item["provider"] for item in created] == ["routerai", "gigachat"]
    assert created[1]["model"] == "GigaChat-3-Ultra"
    await dependencies.close_llm_provider()
