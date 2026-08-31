"""
OpenAI-compatible LLM provider using httpx.
Works with OpenAI, local Qwen/Llama servers, vLLM, Ollama, etc.
"""
import base64
import json
import time
from typing import Any

import httpx

from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage, LLMResponse


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Generic provider that speaks the OpenAI chat-completions protocol.

    Configuration example (from settings):
        base_url: "http://localhost:8080/v1"   # local Qwen
        api_key:  "sk-..."                     # or "none" for local models
        model:    "qwen2.5-72b-instruct"
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        default_system_prompt: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.default_system_prompt = default_system_prompt
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, messages: list[LLMMessage]) -> list[dict]:
        result: list[dict] = []
        if self.default_system_prompt and not any(m.role == "system" for m in messages):
            result.append({"role": "system", "content": self.default_system_prompt})
        for m in messages:
            result.append({"role": m.role, "content": m.content})
        return result

    async def _post(self, payload: dict) -> dict[str, Any]:
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_text(raw: dict) -> str:
        """Достать текст ответа.

        У моделей с рассуждениями (reasoning) полезный ответ не всегда
        оказывается в ``content``: когда бюджет токенов уходит на
        размышления, ``content`` приходит пустым, а текст остаётся в
        ``reasoning``. Без этого запасного варианта вызов выглядел как
        «модель не вернула ответ», хотя ответ был.
        """
        try:
            message = raw["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected API response shape: {raw}") from exc

        content = message.get("content")
        if content:
            return str(content)

        # Внутреннее рассуждение не является ответом пользователю и не должно
        # попадать ни в чат, ни в JSON-анализ. Пустой content обычно означает,
        # что max_tokens закончился до формирования финального ответа.
        if message.get("reasoning") or message.get("reasoning_content"):
            raise ValueError(
                "Модель израсходовала лимит на рассуждение и не вернула "
                "финальный ответ"
            )
        raise ValueError("Модель вернула пустой финальный ответ")

    @staticmethod
    def _extract_usage(raw: dict) -> tuple[int, int]:
        usage = raw.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        t0 = time.time()
        raw = await self._post(payload)
        latency = int((time.time() - t0) * 1000)
        tokens_in, tokens_out = self._extract_usage(raw)
        return LLMResponse(
            content=self._extract_text(raw),
            model=self.model,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            latency_ms=latency,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        """
        Attempt to get structured JSON output.

        Strategy:
        1. Append a system instruction demanding JSON conforming to output_schema.
        2. If the model supports response_format=json_object, use it.
        3. Parse the returned content as JSON; if parsing fails, raise.
        """
        schema_str = json.dumps(output_schema, ensure_ascii=False)
        injection = LLMMessage(
            role="system",
            content=(
                "Отвечай ТОЛЬКО валидным JSON без маркдауна и объяснений. "
                f"Схема ответа: {schema_str}"
            ),
        )
        augmented = [injection] + list(messages)

        payload = {
            "model": self.model,
            "messages": self._build_messages(augmented),
            "temperature": temperature,
            # Flash-модель может потратить несколько тысяч токенов на скрытое
            # рассуждение до JSON. Малый лимит давал пустой content.
            "max_tokens": 16000,
            "response_format": {"type": "json_object"},
        }
        t0 = time.time()
        try:
            raw = await self._post(payload)
        except httpx.HTTPStatusError as exc:
            # Some local servers don't support response_format; retry without it
            if exc.response.status_code == 400:
                payload.pop("response_format", None)
                raw = await self._post(payload)
            else:
                raise
        _ = int((time.time() - t0) * 1000)

        text = self._extract_text(raw)
        # Strip possible markdown fences
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(text)

    async def generate_image_structured(
        self,
        *,
        image: bytes,
        mime_type: str,
        prompt: str,
        output_schema: dict,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2500,
    ) -> dict[str, Any]:
        """Получить JSON-описание изображения через совместимый vision API."""
        if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            raise ValueError("Неподдерживаемый формат изображения")
        data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
        schema = json.dumps(output_schema, ensure_ascii=False)
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Отвечай только валидным JSON без Markdown. "
                        f"Схема результата: {schema}"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            raw = await self._post(payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                payload.pop("response_format", None)
                raw = await self._post(payload)
            else:
                raise
        text = self._extract_text(raw).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)

    async def aclose(self) -> None:
        await self._client.aclose()
