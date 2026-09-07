"""Synthetic full-stack acceptance. Only permitted with mock external providers."""
import asyncio
import os
import time
import httpx

from app.core.config import settings
from app.core.security import hash_password
from app.infrastructure.database.models import User, UserRole
from app.infrastructure.database.session import AsyncSessionLocal, close_db


async def seed():
    if settings.LLM_PROVIDER != "mock" or settings.FIPS_PROVIDER != "mock":
        raise RuntimeError("Smoke test requires mock providers")
    async with AsyncSessionLocal() as session:
        session.add(User(email="smoke@example.com", hashed_password=hash_password("smoke-local-12345"),
                         full_name="Synthetic smoke user", role=UserRole.client, is_active=True))
        await session.commit()
    await close_db()


def run():
    asyncio.run(seed())
    with httpx.Client(base_url=os.environ.get("SMOKE_URL", "http://web:8080"), timeout=30) as http:
        response = http.get("/ready")
        response.raise_for_status()
        assert response.json()["checks"]["worker"]["ok"]
        response = http.post("/api/v1/auth/login/json", json={"email": "smoke@example.com", "password": "smoke-local-12345"})
        response.raise_for_status()
        http.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        response = http.post("/api/v1/clients", json={"type": "individual", "full_name_or_company_name": "Synthetic smoke applicant"})
        response.raise_for_status()
        response = http.post("/api/v1/applications", json={"client_id": response.json()["id"],
            "mark_type": "word", "mark_name": "SMOKETEST", "mark_text": "SMOKETEST",
            "business_description": "Software development", "goods_services_raw": "Software"})
        response.raise_for_status()
        app_id = response.json()["id"]
        response = http.post(f"/api/v1/applications/{app_id}/source-documents",
                            files={"file": ("smoke.txt", b"Synthetic backup verification document", "text/plain")})
        response.raise_for_status()
        response = http.post(f"/api/v1/applications/{app_id}/full-analysis/jobs", json={})
        response.raise_for_status()
        until = time.monotonic() + 150
        while time.monotonic() < until:
            response = http.get(f"/api/v1/applications/{app_id}/full-analysis/jobs/latest")
            response.raise_for_status()
            payload = response.json()
            job = payload.get("job") or payload
            if job.get("status") == "completed":
                print("PASS: nginx -> API -> PostgreSQL queue -> separate worker -> completed")
                return
            if job.get("status") == "failed":
                raise RuntimeError("Synthetic worker job failed")
            time.sleep(1)
        raise RuntimeError("Worker did not complete synthetic job in time")


if __name__ == "__main__":
    run()
