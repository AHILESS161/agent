"""Worker progress probe; a running PID alone is not readiness."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.core.config import settings


def publish_heartbeat(worker_id: str) -> None:
    path = Path(settings.WORKER_HEARTBEAT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps({"worker_id": worker_id, "time": time.time()}), encoding="utf-8")
    os.replace(temp, path)


def check_worker() -> tuple[bool, str | None]:
    try:
        data = json.loads(Path(settings.WORKER_HEARTBEAT_PATH).read_text(encoding="utf-8"))
        age = time.time() - float(data["time"])
        if not data["worker_id"] or not 0 <= age <= settings.WORKER_HEARTBEAT_MAX_AGE:
            return False, "Worker heartbeat is stale"
    except (OSError, ValueError, KeyError, TypeError):
        return False, "Worker heartbeat is unavailable"
    return True, None


async def check_queue() -> tuple[bool, str | None]:
    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from app.infrastructure.database.models import BackgroundJob, JobStatus
    from app.infrastructure.database.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            oldest = await session.scalar(select(func.min(BackgroundJob.created_at)).where(
                BackgroundJob.status.in_([JobStatus.queued, JobStatus.retrying])))
        if oldest:
            age = (datetime.now(timezone.utc) - oldest.replace(tzinfo=timezone.utc)).total_seconds()
            if age > settings.QUEUE_MAX_WAIT_SECONDS:
                return False, "Analysis queue wait exceeds the configured limit"
    except Exception:
        return False, "Analysis queue unavailable"
    return True, None


if __name__ == "__main__":
    raise SystemExit(0 if check_worker()[0] else 1)
