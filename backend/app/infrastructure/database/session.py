"""SQLAlchemy async engine and session factory for SQLite."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""
    pass


def _build_engine() -> AsyncEngine:
    connect_args: dict = {}
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(
        url,
        echo=settings.DEBUG,
        connect_args=connect_args,
        future=True,
    )


engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables. Call on startup."""
    async with engine.begin() as conn:
        from app.infrastructure.database import models  # noqa: F401 — ensures models are registered
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose engine connections. Call on shutdown."""
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
