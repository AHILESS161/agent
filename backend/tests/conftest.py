"""
pytest configuration and shared fixtures for the Trademark Registration System.

Fixture hierarchy:
    engine          — in-memory SQLite engine (function-scoped)
    db_session      — synchronous Session bound to the in-memory DB
    async_session   — AsyncSession for async-aware tests
    client          — FastAPI TestClient with overridden DB dependency
    auth_headers_*  — pre-authenticated headers for each role
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.infrastructure.database.models import (
    ApplicationStatus,
    Client,
    ClientType,
    MarkType,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import Base, get_session
from app.main import app


# ---------------------------------------------------------------------------
# Synchronous in-memory SQLite engine (for unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def engine():
    """Create a fresh in-memory SQLite engine for each test."""
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    yield _engine
    Base.metadata.drop_all(bind=_engine)
    _engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Yield a synchronous SQLAlchemy session bound to the in-memory DB."""
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Async in-memory SQLite engine (for API tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def async_engine():
    """Create an async in-memory SQLite engine shared across all sessions
    of the test (StaticPool keeps the same connection alive, which is required
    for SQLite :memory: to persist data between requests)."""
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session and create tables before the test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with AsyncSessionLocal() as session:
        yield session

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# FastAPI TestClient with dependency overrides
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client(async_engine):
    """
    FastAPI TestClient with the DB dependency overridden to use
    the in-memory SQLite engine.

    Tables are created lazily on the first request via a flag inside the
    dependency — this avoids spinning up an event loop from the sync fixture.
    The same engine (StaticPool) is reused for every session, so data
    committed in one request is visible to the next.
    """
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    tables_created = {"done": False}

    async def override_get_session():
        if not tables_created["done"]:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            tables_created["done"] = True
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    """Отключить ограничение частоты запросов в тестах.

    Тесты обращаются к /auth/login десятки раз подряд с одного адреса
    и упирались бы в лимит. Сам лимитер проверяется отдельно
    в tests/unit/test_rate_limit.py.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    # Lifespan TestClient не должен запускать worker против локальной БД,
    # потому что API dependency в тесте заменена отдельной in-memory БД.
    monkeypatch.setattr(settings, "ANALYSIS_WORKER_MODE", "disabled")


# ---------------------------------------------------------------------------
# Реальные пользователи в тестовой БД
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def api_user_factory(async_engine):
    """Создать пользователя прямо в тестовой БД.

    Через API это больше невозможно: /auth/register закрыт для всех,
    кроме администратора, — эндпоинт принимает поле role и в открытом
    виде позволял назначить себе роль admin.
    """
    async def _create(
        email: str,
        role: UserRole = UserRole.lawyer,
        password: str = "test12345",
    ) -> User:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(
            bind=async_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                full_name=f"Тестовый {role.value}",
                role=role,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _create


def login_headers(client, email: str, password: str = "test12345") -> dict[str, str]:
    """Получить настоящий заголовок авторизации через /auth/login/json."""
    response = client.post(
        "/api/v1/auth/login/json", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _create_user(session: Session, email: str, role: UserRole, password: str = "test123") -> User:
    """Create and persist a User for testing."""
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=f"Test {role.value.title()}",
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_client(session: Session, name: str = 'ООО "Тест"') -> Client:
    """Create and persist a Client for testing."""
    client = Client(
        full_name_or_company_name=name,
        short_name="Тест",
        type=ClientType.company,
        inn="7701234567",
        country="RU",
    )
    session.add(client)
    session.flush()
    return client


def _create_application(
    session: Session,
    client: Client,
    mark_name: str = "ТЕСТ",
    status: ApplicationStatus = ApplicationStatus.draft,
    mark_type: MarkType = MarkType.word,
) -> TrademarkApplicationDraft:
    """Create and persist a TrademarkApplicationDraft for testing."""
    app_obj = TrademarkApplicationDraft(
        client_id=client.id,
        mark_name=mark_name,
        mark_text=mark_name,
        mark_type=mark_type,
        status=status,
        goods_services_raw="Программное обеспечение; консультационные услуги",
        business_description="Тестовое описание",
    )
    session.add(app_obj)
    session.flush()
    return app_obj


# ---------------------------------------------------------------------------
# User fixtures (synchronous, for unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db_session: Session) -> User:
    return _create_user(db_session, "admin@test.ru", UserRole.admin)


@pytest.fixture
def lawyer_user(db_session: Session) -> User:
    return _create_user(db_session, "lawyer@test.ru", UserRole.lawyer)


@pytest.fixture
def manager_user(db_session: Session) -> User:
    return _create_user(db_session, "manager@test.ru", UserRole.manager)


@pytest.fixture
def test_client_entity(db_session: Session) -> Client:
    return _create_client(db_session)


@pytest.fixture
def draft_application(db_session: Session, test_client_entity: Client) -> TrademarkApplicationDraft:
    return _create_application(db_session, test_client_entity)


# ---------------------------------------------------------------------------
# JWT token fixtures (for API tests)
# ---------------------------------------------------------------------------

def _make_token(user_id: int, email: str, role: str) -> str:
    return create_access_token(
        {"sub": str(user_id), "email": email, "role": role},
        expires_delta=timedelta(minutes=60),
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """JWT headers for a synthetic admin user (id=1)."""
    token = _make_token(1, "admin@test.ru", "admin")
    return _auth_headers(token)


@pytest.fixture
def lawyer_headers() -> dict[str, str]:
    """JWT headers for a synthetic lawyer user (id=2)."""
    token = _make_token(2, "lawyer@test.ru", "lawyer")
    return _auth_headers(token)


@pytest.fixture
def manager_headers() -> dict[str, str]:
    """JWT headers for a synthetic manager user (id=3)."""
    token = _make_token(3, "manager@test.ru", "manager")
    return _auth_headers(token)
