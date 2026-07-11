"""
OpenAI-compatible LLM provider using httpx.
Works with OpenAI, local Qwen/Llama servers, vLLM, Ollama, etc.
"""
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
        try:
            return raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected API response shape: {raw}") from exc

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
            "max_tokens": 4096,
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

    async def aclose(self) -> None:
        await self._client.aclose()
