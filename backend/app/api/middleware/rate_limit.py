"""Ограничение частоты запросов.

Простая реализация «скользящее окно в памяти»: для одного процесса
и демо-стенда этого достаточно и не требует Redis. При переходе на
несколько воркеров счётчик нужно вынести в Redis — интерфейс
``RateLimiter`` для этого и выделен.

Защищаются в первую очередь публичные эндпоинты: вход (подбор пароля)
и загрузка файлов (исчерпание диска).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Rule:
    """Ограничение: не более ``limit`` запросов за ``window`` секунд."""

    limit: int
    window: int


# Правила по префиксу пути. Более длинный префикс имеет приоритет.
RULES: dict[str, Rule] = {
    # Подбор пароля — самый чувствительный сценарий.
    "/api/v1/auth/login": Rule(limit=10, window=60),
    "/api/v1/auth/register": Rule(limit=5, window=300),
    # Загрузка файлов: защита от исчерпания дискового пространства.
    "/api/v1/applications": Rule(limit=120, window=60),
    "/api/v1/source-documents": Rule(limit=120, window=60),
}

DEFAULT_RULE = Rule(limit=300, window=60)


class RateLimiter:
    """Счётчик запросов по ключу (скользящее окно)."""

    def __init__(self, max_keys: int = 10000) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._expires: dict[str, float] = {}
        self._max_keys = max_keys
        self._next_cleanup = 0.0

    def check(self, key: str, rule: Rule, now: float | None = None) -> tuple[bool, int]:
        """Вернуть ``(разрешено, сколько секунд ждать)``."""
        now = now if now is not None else time.monotonic()
        if now >= self._next_cleanup or len(self._hits) >= self._max_keys:
            for expired in [k for k, end in self._expires.items() if end <= now]:
                self._hits.pop(expired, None)
                self._expires.pop(expired, None)
            self._next_cleanup = now + 30
        if key not in self._hits:
            if len(self._hits) >= self._max_keys:
                return False, 30  # fail closed; never evict an active quota
            self._hits[key] = deque()
        hits = self._hits[key]
        self._expires[key] = now + rule.window

        cutoff = now - rule.window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= rule.limit:
            retry_after = int(hits[0] + rule.window - now) + 1
            return False, max(retry_after, 1)

        hits.append(now)
        return True, 0

    def reset(self) -> None:
        self._hits.clear()
        self._expires.clear()
        self._next_cleanup = 0.0


_limiter = RateLimiter()


def _rule_for(path: str) -> Rule:
    match = ""
    for prefix in RULES:
        if path.startswith(prefix) and len(prefix) > len(match):
            match = prefix
    return RULES.get(match, DEFAULT_RULE)


def _client_key(request: Request) -> str:
    """Идентификатор клиента.

    За обратным прокси и туннелем реальный адрес приходит
    в X-Forwarded-For.
    """
    # Uvicorn resolves forwarded headers only from its configured trusted proxy.
    # Never parse an untrusted header a second time in application code.
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Ограничивает частоту запросов по IP и пути."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Служебные проверки не ограничиваем: иначе оркестратор
        # решит, что сервис недоступен.
        if request.url.path in ("/health", "/ready", "/api/v1/health"):
            return await call_next(request)

        rule = _rule_for(request.url.path)
        path = request.url.path
        group = next((p for p in sorted(RULES, key=len, reverse=True)
                      if path == p or path.startswith(p + "/")), "other")
        client = _client_key(request)
        allowed, retry_after = _limiter.check(f"{client}:all", DEFAULT_RULE)
        if allowed:
            allowed, retry_after = _limiter.check(f"{client}:{group}", rule)

        if not allowed:
            logger.warning(
                "Превышен лимит запросов",
                path=request.url.path,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": (
                        "Слишком много запросов. "
                        f"Повторите через {retry_after} с."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
