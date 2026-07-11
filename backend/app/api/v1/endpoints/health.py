"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database.session import get_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Basic health check")
async def health() -> JSONResponse:
    """Return a simple liveness probe."""
    return JSONResponse(
        content={
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
        }
    )


@router.get("/detailed", summary="Detailed health check with DB connectivity")
async def health_detailed(
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return a health check that also verifies the database is reachable."""
    db_ok = False
    db_error: str | None = None
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)

    status_str = "ok" if db_ok else "degraded"
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": status_str,
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "database": {
                "ok": db_ok,
                "error": db_error,
            },
        },
    )
