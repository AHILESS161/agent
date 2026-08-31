"""GigaChat REST provider with OAuth token refresh."""

from __future__ import annotations

import asyncio
import json
import random
import ssl
import time
from typing import Any
from uuid import uuid4

import httpx

from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage, LLMResponse


class GigaChatStructuredOutputError(ValueError):
    """GigaChat returned an incomplete or invalid structured response."""


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
        min_request_interval: float = 1.25,
        max_retries: int = 5,
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
        self.min_request_interval = max(0.0, min_request_interval)
        self.max_retries = max(1, max_retries)
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
        # Полный анализ делает несколько вызовов модели. Все они проходят через
        # одну очередь, чтобы параллельные HTTP-запросы пользователя не создавали
        # всплеск, на который GigaChat отвечает 429.
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

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
        force_token_refresh = False
        token_was_refreshed = False
        retryable_statuses = {429, 500, 502, 503, 504}

        async with self._request_lock:
            for attempt in range(self.max_retries):
                since_last = time.monotonic() - self._last_request_at
                if since_last < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - since_last)
                try:
                    token = await self._get_access_token(
                        force_refresh=force_token_refresh
                    )
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
                    self._last_request_at = time.monotonic()
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(min(2.0 * (2**attempt), 30.0))
                    continue

                if response.status_code == 401 and not token_was_refreshed:
                    self._access_token = None
                    self._access_token_expires_at = 0
                    force_token_refresh = True
                    token_was_refreshed = True
                    continue

                if (
                    response.status_code in retryable_statuses
                    and attempt < self.max_retries - 1
                ):
                    retry_after = response.headers.get("Retry-After")
                    fallback = min(2.0 * (2**attempt), 30.0)
                    try:
                        delay = (
                            min(max(float(retry_after), 0.0), 30.0)
                            if retry_after
                            else fallback
                        )
                    except ValueError:
                        delay = fallback
                    # Небольшой jitter не даёт нескольким процессам повторить
                    # запрос одновременно после одного и того же лимита.
                    jitter = random.uniform(0.0, min(0.5, delay * 0.2))
                    await asyncio.sleep(delay + jitter)
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
    def _ensure_not_truncated(raw: dict[str, Any]) -> None:
        try:
            finish_reason = str(raw["choices"][0].get("finish_reason") or "").casefold()
        except (KeyError, IndexError, TypeError):
            return
        if finish_reason in {"length", "max_tokens", "token_limit"}:
            raise GigaChatStructuredOutputError(
                "GigaChat truncated the structured response at the token limit"
            )

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
            "max_tokens": 16000,
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
        try:
            self._ensure_not_truncated(raw)
            return self._parse_json(self._extract_text(raw))
        except (json.JSONDecodeError, GigaChatStructuredOutputError) as exc:
            raise GigaChatStructuredOutputError(
                "GigaChat returned incomplete structured JSON"
            ) from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
        if self._owns_auth_client:
            await self._auth_client.aclose()
