"""Persistent admission budgets shared by API and worker processes."""
from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from app.core.config import settings
from app.infrastructure.database.models import User, SourceDocument, TrademarkApplicationDraft, ResourceBudget
from app.infrastructure.database.session import AsyncSessionLocal

actor_id: ContextVar[int | None] = ContextVar("resource_actor", default=None)
_llm_slots = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)


async def lock_user(session, user_id: int) -> None:
    # Every upload/create/enqueue uses the same lock through transaction commit.
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def lock_queue(session) -> None:
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        await session.execute(text("SELECT pg_advisory_xact_lock(2026090612)"))


async def check_storage_quota(session, user_id: int, size: int) -> None:
    await lock_user(session, user_id)
    count, used = (await session.execute(select(func.count(SourceDocument.id),
        func.coalesce(func.sum(SourceDocument.file_size), 0)).where(
        SourceDocument.uploaded_by_user_id == user_id))).one()
    if count >= settings.USER_MAX_DOCUMENTS or used + size > settings.USER_STORAGE_MB * 1024 * 1024:
        raise HTTPException(429, "Квота документов исчерпана. Удалите ненужные файлы или обратитесь к администратору")


async def check_application_quota(session, user_id: int) -> None:
    await lock_user(session, user_id)
    count = await session.scalar(select(func.count(TrademarkApplicationDraft.id)).where(
        TrademarkApplicationDraft.created_by_user_id == user_id))
    if count >= settings.USER_MAX_APPLICATIONS:
        raise HTTPException(429, "Достигнут лимит заявок пользователя")


async def reserve_llm_budget(units: int, user_id: int | None, session_factory=AsyncSessionLocal) -> None:
    day = datetime.now(timezone.utc).date().isoformat()
    async with session_factory() as session:
        if session.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        for owner, limit in (("global", settings.LLM_DAILY_GLOBAL_BUDGET),
                             (f"user:{user_id}", settings.LLM_DAILY_USER_BUDGET)):
            key = f"{day}:{owner}"
            await session.execute(insert(ResourceBudget).values(key=key, spent=0).on_conflict_do_nothing())
            result = await session.execute(update(ResourceBudget).where(
                ResourceBudget.key == key, ResourceBudget.spent + units <= limit
            ).values(spent=ResourceBudget.spent + units))
            if result.rowcount != 1:
                await session.rollback()
                raise HTTPException(429, "Дневной бюджет анализа исчерпан. Повторите завтра или обратитесь к администратору")
        await session.commit()


async def budgeted_post(client, *args, **kwargs):
    if settings.ENVIRONMENT != "production":
        return await client.post(*args, **kwargs)
    payload = kwargs.get("json", {})
    max_tokens = int(payload.get("max_tokens", 0))
    if not 0 < max_tokens <= 32768:
        raise HTTPException(429, "Недопустимый лимит ответа модели")
    # Conservative upper estimate, including vision data. Failed attempts are charged.
    units = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + max_tokens
    try:
        await asyncio.wait_for(_llm_slots.acquire(), timeout=1)
    except TimeoutError as exc:
        raise HTTPException(429, "Анализ занят. Повторите позже") from exc
    try:
        await reserve_llm_budget(units, actor_id.get())
        return await client.post(*args, **kwargs)
    finally:
        _llm_slots.release()
