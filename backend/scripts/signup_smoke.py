"""CI-only client signup regression against PostgreSQL, with no real mail."""
import asyncio
import uuid
import httpx
from sqlalchemy import func, select

from app.core.config import settings
from app.infrastructure.database.models import User, UserRole
from app.infrastructure.database.session import AsyncSessionLocal


async def main():
    if settings.LLM_PROVIDER != "mock" or settings.FIPS_PROVIDER != "mock":
        raise RuntimeError("Signup smoke is restricted to the isolated mock-provider CI stack")
    from app.api.v1.endpoints import signup
    from app.main import app
    settings.PUBLIC_SIGNUP_ENABLED = True
    settings.SMTP_HOST = settings.SMTP_USERNAME = settings.SMTP_PASSWORD = settings.SMTP_FROM = "ci@example.com"
    sent = []
    async def capture(email, token):
        sent.append(token)
    signup.send_confirmation_email = capture
    email = f"ci-{uuid.uuid4().hex}@example.com"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as client:
        for _ in range(2):
            response = await client.post("/api/v1/auth/signup/request", json={"email": email})
            assert response.status_code == 202, response.status_code
        async def confirm(token):
            return await client.post("/api/v1/auth/signup/confirm", json={"token": token,
                "full_name": "CI client", "password": "synthetic-ci-password"})
        responses = await asyncio.gather(*(confirm(token) for token in sent))
        assert sorted(r.status_code for r in responses) == [201, 400]
        assert (await confirm(sent[0])).status_code == 400
    async with AsyncSessionLocal() as session:
        assert await session.scalar(select(func.count(User.id)).where(User.email == email)) == 1
        assert await session.scalar(select(User.role).where(User.email == email)) == UserRole.client
    print("PASS: concurrent PostgreSQL confirmations create exactly one client; replay denied")


if __name__ == "__main__":
    asyncio.run(main())
