"""GigaChat REST provider with OAuth token refresh."""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from typing import Any
from uuid import uuid4

import httpx

from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage, LLMResponse


class GigaChatProvider(BaseLLMProvider):
    """Call GigaChat's v1 chat API using an Authorization Key."""

    def __init__(
        self,
        authorization_key: str,
        model: str = "GigaChat-3-Ultra",
        base_url: str = "https://api.giga.chat/v1",
        auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        scope: str = "GIGACHAT_API_PERS",
        timeout: float = 120.0,
        verify_ssl: bool = True,
        ca_bundle_file: str | None = None,
        default_system_prompt: str | None = None,
        client: httpx.AsyncClient | None = None,
        auth_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not authorization_key or not authorization_key.strip():
            raise ValueError("GigaChat Authorization Key is required")

        self.authorization_key = authorization_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.auth_url = auth_url
        self.scope = scope
        self.timeout = timeout
        self.default_system_prompt = default_system_prompt
        ssl_verification: bool | ssl.SSLContext = verify_ssl
        if verify_ssl and ca_bundle_file:
            ssl_context = ssl.create_default_context()
            ssl_context.load_verify_locations(cafile=ca_bundle_file)
            ssl_verification = ssl_context
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, verify=ssl_verification
        )
        self._auth_client = auth_client or httpx.AsyncClient(
            timeout=self.timeout, verify=ssl_verification
        )
        self._owns_client = client is None
        self._owns_auth_client = auth_client is None
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def _build_messages(self, messages: list[LLMMessage]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if self.default_system_prompt and not any(m.role == "system" for m in messages):
            result.append({"role": "system", "content": self.default_system_prompt})
        result.extend({"role": message.role, "content": message.content} for message in messages)
        return result

    @staticmethod
    def _normalise_expiry(value: Any) -> float:
        """Return an epoch timestamp; the API has used seconds and milliseconds."""
        try:
            expires_at = float(value)
        except (TypeError, ValueError):
            return time.time() + 25 * 60
        if expires_at > 10_000_000_000:
            expires_at /= 1000
        return expires_at

    async def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and time.time() < self._access_token_expires_at - 60
        ):
            return self._access_token

        async with self._token_lock:
            if (
                not force_refresh
                and self._access_token
                and time.time() < self._access_token_expires_at - 60
            ):
                return self._access_token

            response = await self._auth_client.post(
                self.auth_url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Basic {self.authorization_key}",
                    "RqUID": str(uuid4()),
                },
                data={"scope": self.scope},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise ValueError("GigaChat OAuth response did not contain access_token")
            self._access_token = str(token)
            self._access_token_expires_at = self._normalise_expiry(payload.get("expires_at"))
            return self._access_token

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_attempts = 3
        force_token_refresh = False
        token_was_refreshed = False
        retryable_statuses = {429, 500, 502, 503, 504}

        for attempt in range(max_attempts):
            try:
                token = await self._get_access_token(force_refresh=force_token_refresh)
                force_token_refresh = False
                response = await self._client.post(
                    "/chat/completions",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
                continue

            if response.status_code == 401 and not token_was_refreshed:
                self._access_token = None
                self._access_token_expires_at = 0
                force_token_refresh = True
                token_was_refreshed = True
                continue

            if response.status_code in retryable_statuses and attempt < max_attempts - 1:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 5.0) if retry_after else 0.5 * (2**attempt)
                except ValueError:
                    delay = 0.5 * (2**attempt)
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("GigaChat request failed after retries")

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        try:
            return str(raw["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unexpected GigaChat response shape") from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
            )
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("GigaChat structured response must be a JSON object")
        return parsed

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
        started_at = time.perf_counter()
        raw = await self._post(payload)
        usage = raw.get("usage") or {}
        return LLMResponse(
            content=self._extract_text(raw),
            model=str(raw.get("model") or self.model),
            tokens_input=int(usage.get("prompt_tokens") or 0),
            tokens_output=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": 4096,
            "response_format": {
                "type": "json_schema",
                "schema": output_schema,
                "strict": True,
            },
        }
        try:
            raw = await self._post(payload)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            schema_text = json.dumps(output_schema, ensure_ascii=False)
            payload.pop("response_format")
            payload["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "Ответь только валидным JSON без Markdown. "
                        f"JSON должен соответствовать схеме: {schema_text}"
                    ),
                },
                *payload["messages"],
            ]
            raw = await self._post(payload)
        return self._parse_json(self._extract_text(raw))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
        if self._owns_auth_client:
            await self._auth_client.aclose()
