"""
LLM Provider Factory — creates the appropriate provider based on configuration.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.llm.base import BaseLLMProvider


class LLMProviderFactory:
    """
    Creates and returns an LLM provider instance from a configuration dict.

    Supported provider types:
        - "mock"       → MockLLMProvider (no network, canned responses)
        - "local"      → OpenAICompatibleProvider pointed at a local server (e.g. Qwen via vLLM)
        - "openai"     → OpenAICompatibleProvider pointed at api.openai.com
        - "routerai"   → OpenAICompatibleProvider pointed at https://routerai.ru/api/v1
                         (OpenAI-compatible proxy, default model tencent/hy3)
        - "anthropic"  → (future) AnthropicProvider stub
        - "deepseek"   → OpenAICompatibleProvider pointed at DeepSeek API

    Config shape:
        {
            "provider": "mock" | "local" | "openai" | "routerai" | "anthropic" | "deepseek",

            # required for local/openai/routerai/deepseek:
            "base_url": "http://localhost:8080/v1",
            "api_key": "sk-...",
            "model": "qwen2.5-72b-instruct",

            # optional:
            "timeout": 120.0,
            "default_system_prompt": "...",
        }
    """

    # Provider-specific defaults (used only if value is not provided in config)
    PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
        "gigachat": {
            "base_url": "https://api.giga.chat/v1",
            "model": "GigaChat-3-Ultra",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
        "routerai": {
            "base_url": "https://routerai.ru/api/v1",
            "model": "tencent/hy3",
        },
        "local": {
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5-72b-instruct",
        },
    }

    @staticmethod
    def create(config: dict) -> "BaseLLMProvider":
        provider_type: str = config.get("provider", "mock").lower()

        if provider_type == "mock":
            from app.infrastructure.llm.mock_provider import MockLLMProvider

            return MockLLMProvider()

        if provider_type == "gigachat":
            from app.infrastructure.llm.gigachat_provider import GigaChatProvider

            defaults = LLMProviderFactory.PROVIDER_DEFAULTS["gigachat"]
            authorization_key = config.get("authorization_key") or config.get("api_key")
            return GigaChatProvider(
                authorization_key=authorization_key or "",
                base_url=config.get("base_url") or defaults["base_url"],
                model=config.get("model") or defaults["model"],
                auth_url=config.get("auth_url")
                or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                scope=config.get("scope") or "GIGACHAT_API_PERS",
                timeout=float(config.get("timeout", 120.0)),
                verify_ssl=bool(config.get("verify_ssl", True)),
                ca_bundle_file=config.get("ca_bundle_file"),
                default_system_prompt=config.get("default_system_prompt"),
            )

        if provider_type in ("local", "openai", "deepseek", "routerai"):
            from app.infrastructure.llm.openai_compatible_provider import (
                OpenAICompatibleProvider,
            )

            defaults = LLMProviderFactory.PROVIDER_DEFAULTS.get(provider_type, {})
            base_url = (
                config.get("base_url")
                or defaults.get("base_url", "https://api.openai.com/v1")
            )
            api_key = config.get("api_key", "none")
            model = config.get("model") or defaults.get("model", "gpt-4o")
            timeout = float(config.get("timeout", 120.0))
            default_system_prompt = config.get("default_system_prompt")

            return OpenAICompatibleProvider(
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
                default_system_prompt=default_system_prompt,
            )

        if provider_type == "anthropic":
            # Stub — raise informative error until AnthropicProvider is implemented
            raise NotImplementedError(
                "AnthropicProvider is not yet implemented. "
                "Use provider='mock' or provider='openai'."
            )

        raise ValueError(
            f"Unknown LLM provider type: '{provider_type}'. "
            "Supported values: mock, local, openai, routerai, deepseek, gigachat, anthropic."
        )
