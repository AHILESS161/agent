"""structlog configuration with request_id and correlation_id support."""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, MutableMapping

import structlog
from structlog.types import EventDict, WrappedLogger

# Context variables for request-scoped identifiers
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def add_request_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject request_id and correlation_id from context vars into every log record."""
    request_id = request_id_var.get("")
    correlation_id = correlation_id_var.get("")
    if request_id:
        event_dict["request_id"] = request_id
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


import re

# Персональные данные и секреты, которые не должны попадать в логи
# в открытом виде. Логи могут выгружаться, пересылаться и храниться
# дольше самих документов.
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ИНН физического лица (12 цифр) — оставляем последние 2 знака.
    (re.compile(r"(?<!\d)(\d{10})(\d{2})(?!\d)"), r"**********\2"),
    # СНИЛС
    (re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}\s?\d{2}(?!\d)"), "***-***-*** **"),
    # Серия и номер паспорта. Разделитель обязателен: без него шаблон
    # съедал 10-значный ИНН юридического лица (4+6 цифр подряд).
    (re.compile(r"(?<!\d)\d{4}(?:\s+№\s*|\s*№\s*|\s+)\d{6}(?!\d)"), "**** ******"),
    # Электронная почта
    (re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)"), r"***@\1"),
    # Токены Bearer и ключи API
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"(sk-)[A-Za-z0-9._\-]{8,}"), r"\1***"),
]

# Ключи, значение которых маскируется целиком.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "hashed_password",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "api_key",
        "secret",
        "secret_key",
        "authorization",
    }
)


def _mask_text(value: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _mask_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "***"
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_value(key, v) for v in value]
    return value


def mask_sensitive_data(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Замаскировать персональные данные и секреты в записи лога.

    Система обрабатывает выписки с ФИО, ИНН и паспортными данными.
    Их попадание в логи — отдельная утечка, не связанная с доступом
    к самим документам.
    """
    return {key: _mask_value(key, value) for key, value in event_dict.items()}


def add_log_level_upper(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add uppercase log level."""
    event_dict["level"] = method_name.upper()
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for the application."""

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_request_context,
        structlog.stdlib.add_logger_name,
        add_log_level_upper,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Маскирование выполняется последним — после того как все
        # процессоры добавили свои поля.
        mask_sensitive_data,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger."""
    return structlog.get_logger(name)  # type: ignore[return-value]


def set_request_id(value: str | None = None) -> str:
    """Set request_id in context var and return it."""
    rid = value or str(uuid.uuid4())
    request_id_var.set(rid)
    return rid


def set_correlation_id(value: str | None = None) -> str:
    """Set correlation_id in context var and return it."""
    cid = value or str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid
