"""SQLAlchemy async engine and session factory for SQLite."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy import event
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
        # Полный правовой анализ выполняет внешние запросы и может держать
        # транзакцию дольше обычного HTTP-запроса. SQLite по умолчанию ждёт
        # освобождения записи всего пять секунд, после чего отвечает
        # ``database is locked``. Для локального/demo режима даём активной
        # операции завершиться вместо случайного HTTP 500.
        connect_args["timeout"] = 120
    return create_async_engine(
        url,
        echo=settings.DEBUG,
        connect_args=connect_args,
        future=True,
    )


engine: AsyncEngine = _build_engine()


if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            # WAL позволяет экрану читать готовое заключение, пока новый
            # анализ записывает результаты. busy_timeout дублирует timeout
            # на уровне SQLite для всех подключений.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=120000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def check_schema() -> tuple[bool, str | None]:
    """Проверить, что БД доступна и схема накатана миграциями.

    Схему создаёт Alembic (``alembic upgrade head``), а не приложение:
    ``create_all()`` при старте не версионируется и молча расходится
    с миграциями. Здесь только проверка — никакого DDL.

    Возвращает ``(ok, error)``.
    """
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            revision = result.scalar()
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"БД недоступна или схема не инициализирована: {exc}. "
            "Выполните: alembic upgrade head"
        )

    if not revision:
        return False, (
            "Таблица alembic_version пуста — миграции не применялись. "
            "Выполните: alembic upgrade head"
        )
    return True, None


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
