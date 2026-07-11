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
