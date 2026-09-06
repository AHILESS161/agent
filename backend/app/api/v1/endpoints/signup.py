"""Public client signup. Privileged account creation remains admin-only."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.infrastructure.database.models import PendingSignup, ResourceBudget, User, UserRole
from app.infrastructure.database.session import get_session
from app.services.signup_mail import signup_available, send_confirmation_email

router = APIRouter(prefix="/auth/signup", tags=["auth"])
GENERIC_MESSAGE = "Если адрес доступен для регистрации, письмо отправлено. Проверьте входящие и спам."


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=255)


class SignupConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=100)
    password: str = Field(min_length=8, max_length=1024)
    full_name: str = Field(min_length=1, max_length=255)


def _enabled():
    if not signup_available():
        raise HTTPException(503, "Регистрация временно недоступна. Попробуйте позже.")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _reserve_mail(session: AsyncSession, email: str, ip: str):
    now = datetime.now(timezone.utc)
    day, hour = now.strftime("%Y-%m-%d"), now.strftime("%H")
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    for suffix, limit in (("global", settings.SIGNUP_DAILY_GLOBAL_LIMIT),
        ("email:" + _digest(email)[:32], settings.SIGNUP_DAILY_EMAIL_LIMIT),
        ("ip:" + hour + ":" + _digest(ip)[:32], settings.SIGNUP_HOURLY_IP_LIMIT)):
        key = "signup:" + day + ":" + suffix
        await session.execute(insert(ResourceBudget).values(key=key, spent=0).on_conflict_do_nothing())
        changed = await session.execute(update(ResourceBudget).where(
            ResourceBudget.key == key, ResourceBudget.spent < limit).values(spent=ResourceBudget.spent + 1))
        if changed.rowcount != 1:
            await session.rollback()
            raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")
    # Admission is committed even if delivery fails, preventing retries from bypassing limits.
    await session.execute(delete(ResourceBudget).where(ResourceBudget.key.like("signup:%"),
        ResourceBudget.key < "signup:" + (now - timedelta(days=2)).strftime("%Y-%m-%d")))
    await session.execute(delete(PendingSignup).where(PendingSignup.expires_at < now))
    await session.commit()


@router.get("/config")
async def config():
    return {"enabled": signup_available()}


@router.post("/request", status_code=202)
async def request_signup(payload: SignupRequest, request: Request,
                         session: AsyncSession = Depends(get_session)):
    _enabled()
    email = str(payload.email).lower()
    await _reserve_mail(session, email, request.client.host if request.client else "unknown")
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)):
        return {"message": GENERIC_MESSAGE}
    token = secrets.token_urlsafe(32)
    session.add(PendingSignup(token_hash=_digest(token), email=email,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    # SMTP must not hold a pooled database connection while waiting on the network.
    await session.commit()
    try:
        await send_confirmation_email(email, token)
    except Exception:
        await session.execute(delete(PendingSignup).where(PendingSignup.token_hash == _digest(token)))
        await session.commit()
        raise HTTPException(503, "Не удалось отправить письмо. Попробуйте позже.") from None
    return {"message": GENERIC_MESSAGE}


@router.post("/confirm", status_code=201)
async def confirm_signup(payload: SignupConfirm, session: AsyncSession = Depends(get_session)):
    _enabled()
    token_hash = _digest(payload.token)
    pending = await session.get(PendingSignup, token_hash)
    invalid = HTTPException(400, "Ссылка недействительна или устарела. Запросите новое письмо.")
    if pending is None:
        raise invalid
    email = pending.email
    if session.bind.dialect.name == "postgresql":
        # All confirmations for this mailbox share a transaction lock, including different links.
        key = int.from_bytes(hashlib.sha256(email.encode()).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    claimed = await session.execute(delete(PendingSignup).where(
        PendingSignup.token_hash == token_hash,
        PendingSignup.expires_at > datetime.now(timezone.utc))
        .execution_options(synchronize_session=False).returning(PendingSignup.email))
    if claimed.scalar_one_or_none() is None:
        raise invalid
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise invalid
    name = payload.full_name.strip()
    if not name:
        raise HTTPException(422, "Укажите имя")
    session.add(User(email=email, full_name=name, hashed_password=hash_password(payload.password),
                     role=UserRole.client, is_active=True))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise invalid from None
    await session.execute(delete(PendingSignup).where(PendingSignup.email == email))
    return {"message": "Почта подтверждена. Аккаунт создан — теперь можно войти."}
