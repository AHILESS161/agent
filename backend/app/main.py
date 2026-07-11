"""FastAPI application entry point."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger, set_correlation_id, set_request_id
from app.infrastructure.database.session import close_db, init_db

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting up", app=settings.APP_NAME, version=settings.APP_VERSION)
    await init_db()
    logger.info("Database tables created / verified")
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

    @app.get("/", tags=["system"], include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            content={"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}
        )

    return app


app = create_app()
