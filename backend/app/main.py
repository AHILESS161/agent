"""FastAPI application entry point."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger, set_correlation_id, set_request_id
from app.infrastructure.database.session import check_schema, close_db

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting up", app=settings.APP_NAME, version=settings.APP_VERSION)
    # Схему создаёт Alembic, а не приложение. При старте только проверяем.
    schema_ok, schema_error = await check_schema()
    if schema_ok:
        logger.info("Схема БД проверена")
    else:
        # Не валим процесс: приложение должно подняться и честно
        # сообщить о неготовности через /ready, а не падать в рестарт-цикл.
        logger.error("Схема БД не готова", error=schema_error)
    yield
    logger.info("Shutting down")
    await close_db()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Backend API for the Russian Trademark Registration Automation System. "
            "Handles AI-assisted classification, legal review, conflict search, "
            "document generation, and submission to FIPS."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ---- CORS ----------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Ограничение частоты запросов ----------------------------------------
    app.add_middleware(RateLimitMiddleware)

    # ---- Request ID middleware ------------------------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        set_request_id(request_id)
        set_correlation_id(correlation_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # ---- Exception handlers --------------------------------------------------
    register_exception_handlers(app)

    # ---- Routers -------------------------------------------------------------
    app.include_router(api_router)

    # ---- Health check --------------------------------------------------------
    @app.get("/health", tags=["system"])
    async def health_check() -> JSONResponse:
        return JSONResponse(
            content={
                "status": "ok",
                "app": settings.APP_NAME,
                "version": settings.APP_VERSION,
            }
        )

    @app.get("/ready", tags=["system"], summary="Готовность к обслуживанию запросов")
    async def readiness_check() -> JSONResponse:
        """Проверяет обязательные зависимости: БД и файловое хранилище.

        В отличие от /health (процесс жив) отвечает 503, если система
        не способна обслуживать запросы.
        """
        from app.services.file_storage import check_storage

        checks: dict[str, dict[str, object]] = {}

        db_ok, db_error = await check_schema()
        checks["database"] = {"ok": db_ok, "error": db_error}

        storage_ok, storage_error = check_storage()
        checks["file_storage"] = {"ok": storage_ok, "error": storage_error}

        all_ok = all(bool(c["ok"]) for c in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={
                "status": "ready" if all_ok else "not_ready",
                "app": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "checks": checks,
            },
        )

    @app.get("/", tags=["system"], include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            content={"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}
        )

    return app


app = create_app()
