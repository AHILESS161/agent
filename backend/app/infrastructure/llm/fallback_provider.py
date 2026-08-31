"""Надёжный текстовый LLM-провайдер с резервным маршрутом.

Основной провайдер используется всегда первым. GigaChat вызывается только если
основной запрос завершился ошибкой, превысил лимит времени либо если вызывающий
анализатор явно попросил повторить запрос после невалидного структурированного
ответа. Ошибка резервного провайдера не маскируется: её обработает существующий
контур незавершённой проверки.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.logging import get_logger
from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = get_logger(__name__)
T = TypeVar("T")


class FallbackLLMProvider(BaseLLMProvider):
    """Сначала вызывает primary, при сбое — fallback."""

    def __init__(
        self,
        primary: BaseLLMProvider,
        fallback: BaseLLMProvider,
        *,
        primary_timeout: float = 180.0,
        fallback_timeout: float = 75.0,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_timeout = primary_timeout
        self.fallback_timeout = fallback_timeout
        self.model = getattr(primary, "model", primary.__class__.__name__)
        self.fallback_model = getattr(fallback, "model", fallback.__class__.__name__)

    async def _with_fallback(
        self,
        primary_call: Callable[[], Awaitable[T]],
        fallback_call: Callable[[], Awaitable[T]],
        *,
        operation: str,
    ) -> T:
        try:
            return await asyncio.wait_for(primary_call(), timeout=self.primary_timeout)
        except TimeoutError:
            logger.warning(
                "Основная LLM превысила лимит, используется GigaChat",
                operation=operation,
                primary_model=self.model,
                timeout=self.primary_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Основная LLM недоступна, используется GigaChat",
                operation=operation,
                primary_model=self.model,
                error=type(exc).__name__,
            )

        return await asyncio.wait_for(fallback_call(), timeout=self.fallback_timeout)

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self._with_fallback(
            lambda: self.primary.generate(messages, temperature, max_tokens),
            lambda: self.fallback.generate(messages, temperature, max_tokens),
            operation="generate",
        )

    async def generate_fallback(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Явно вызвать резерв после синтаксически неверного ответа primary."""
        logger.warning(
            "Ответ основной LLM отклонён проверкой, используется GigaChat",
            operation="generate_validation_retry",
            primary_model=self.model,
        )
        return await asyncio.wait_for(
            self.fallback.generate(messages, temperature, max_tokens),
            timeout=self.fallback_timeout,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        return await self._with_fallback(
            lambda: self.primary.generate_structured(messages, output_schema, temperature),
            lambda: self.fallback.generate_structured(messages, output_schema, temperature),
            operation="generate_structured",
        )

    def response_used_fallback(self, response: Any) -> bool:
        # GigaChat добавляет к имени ревизию, например
        # ``GigaChat-3-Ultra:32.9.23.6``.
        response_model = str(getattr(response, "model", "") or "")
        return response_model == self.fallback_model or response_model.startswith(
            f"{self.fallback_model}:"
        )

    async def aclose(self) -> None:
        for provider in (self.primary, self.fallback):
            close = getattr(provider, "aclose", None)
            if callable(close):
                await close()
