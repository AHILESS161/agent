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
        - "anthropic"  → (future) AnthropicProvider stub
        - "deepseek"   → OpenAICompatibleProvider pointed at DeepSeek API

    Config shape:
        {
            "provider": "mock" | "local" | "openai" | "anthropic" | "deepseek",

            # required for local/openai/deepseek:
            "base_url": "http://localhost:8080/v1",
            "api_key": "sk-...",
            "model": "qwen2.5-72b-instruct",

            # optional:
            "timeout": 120.0,
            "default_system_prompt": "...",
        }
    """

    @staticmethod
    def create(config: dict) -> "BaseLLMProvider":
        provider_type: str = config.get("provider", "mock").lower()

        if provider_type == "mock":
            from app.infrastructure.llm.mock_provider import MockLLMProvider

            return MockLLMProvider()

        if provider_type in ("local", "openai", "deepseek"):
            from app.infrastructure.llm.openai_compatible_provider import (
                OpenAICompatibleProvider,
            )

            base_url = config.get("base_url", "https://api.openai.com/v1")
            api_key = config.get("api_key", "none")
            model = config.get("model", "gpt-4o")
            timeout = float(config.get("timeout", 120.0))
            default_system_prompt = config.get("default_system_prompt")

            # Provider-specific defaults
            if provider_type == "deepseek":
                base_url = config.get("base_url", "https://api.deepseek.com/v1")
                model = config.get("model", "deepseek-chat")

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
            "Supported values: mock, local, openai, deepseek, anthropic."
        )
