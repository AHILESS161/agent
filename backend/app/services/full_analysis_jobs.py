"""Надёжная БД-очередь полного анализа и worker с арендой заданий.

HTTP-процесс только создаёт строку ``BackgroundJob``. Встроенный worker удобен
для локальной разработки, а production запускает тот же цикл отдельным
процессом. Атомарный compare-and-swap не позволяет двум процессам одновременно
владеть одним заданием; heartbeat продлевает аренду, а просроченная аренда
может быть безопасно подхвачена другим процессом.
"""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update

from app.api.dependencies import get_llm_provider, get_registry_provider
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    AuditLog,
    BackgroundJob,
    JobStatus,
    TrademarkApplicationDraft,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.full_analysis import run_full_analysis

logger = get_logger(__name__)

FULL_ANALYSIS_JOB_TYPE = "full_analysis"
ACTIVE_JOB_STATUSES = {JobStatus.queued, JobStatus.running, JobStatus.retrying}


class JobLeaseLost(RuntimeError):
    """Worker больше не владеет заданием и не вправе сохранять итог."""


@dataclass(frozen=True)
class ClaimedJob:
    job_id: int
    attempt_token: str
    recovered: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def job_payload(job: BackgroundJob) -> dict[str, Any]:
    return dict(job.payload_json or {})


def job_deduplication_key(application_id: int) -> str:
    return f"{FULL_ANALYSIS_JOB_TYPE}:{application_id}"


def serialize_analysis_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job_payload(job)
    return {
        "id": job.id,
        "application_id": payload.get("application_id"),
        "status": job.status.value,
        "progress": int(payload.get("progress") or 0),
        "current_step": payload.get("current_step") or "queued",
        "message": payload.get("message") or "Проверка поставлена в очередь",
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "error_message": job.error_message,
        "result": job.result_json,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _claimable(now: datetime):
    ready = and_(
        BackgroundJob.status.in_((JobStatus.queued, JobStatus.retrying)),
        or_(BackgroundJob.available_at.is_(None), BackgroundJob.available_at <= now),
    )
    expired = and_(
        BackgroundJob.status == JobStatus.running,
        or_(
            BackgroundJob.lease_expires_at.is_(None),
            BackgroundJob.lease_expires_at <= now,
        ),
    )
    return or_(ready, expired)


async def claim_next_analysis_job(
    *,
    worker_id: str,
    session_factory=AsyncSessionLocal,
    lease_seconds: int | None = None,
) -> ClaimedJob | None:
    """Атомарно арендовать одно готовое задание."""

    now = _utcnow()
    lease_until = now + timedelta(
        seconds=lease_seconds or settings.ANALYSIS_JOB_LEASE_SECONDS
    )
    async with session_factory() as session:
        candidates = list(
            (
                await session.execute(
                    select(BackgroundJob.id, BackgroundJob.status)
                    .where(
                        BackgroundJob.job_type == FULL_ANALYSIS_JOB_TYPE,
                        _claimable(now),
                    )
                    .order_by(BackgroundJob.created_at, BackgroundJob.id)
                    .limit(20)
                )
            ).all()
        )

        for job_id, previous_status in candidates:
            token = uuid.uuid4().hex
            result = await session.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.id == job_id,
                    BackgroundJob.job_type == FULL_ANALYSIS_JOB_TYPE,
                    _claimable(now),
                )
                .values(
                    status=JobStatus.running,
                    worker_id=worker_id,
                    attempt_token=token,
                    heartbeat_at=now,
                    lease_expires_at=lease_until,
                    available_at=None,
                    started_at=func.coalesce(BackgroundJob.started_at, now),
                    completed_at=None,
                    error_message=None,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                await session.rollback()
                continue

            recovered = previous_status is JobStatus.running
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                await session.rollback()
                continue
            payload = job_payload(job)
            job.payload_json = {
                **payload,
                "progress": max(2, int(payload.get("progress") or 0)),
                "current_step": "preparing",
                "message": (
                    "Продолжаем проверку после прерванного запуска"
                    if recovered
                    else "Готовим данные для проверки"
                ),
                "recovered_from_expired_lease": recovered,
            }
            await session.commit()
            return ClaimedJob(job_id=job_id, attempt_token=token, recovered=recovered)
    return None


async def renew_job_lease(
    job_id: int,
    attempt_token: str,
    *,
    worker_id: str,
    session_factory=AsyncSessionLocal,
    lease_seconds: int | None = None,
) -> bool:
    now = _utcnow()
    lease_until = now + timedelta(
        seconds=lease_seconds or settings.ANALYSIS_JOB_LEASE_SECONDS
    )
    async with session_factory() as session:
        result = await session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status == JobStatus.running,
                BackgroundJob.worker_id == worker_id,
                BackgroundJob.attempt_token == attempt_token,
            )
            .values(heartbeat_at=now, lease_expires_at=lease_until)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
        return result.rowcount == 1


async def _release_interrupted_job(
    claimed: ClaimedJob,
    *,
    session_factory=AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        job = await session.get(BackgroundJob, claimed.job_id)
        if (
            job is None
            or job.status is not JobStatus.running
            or job.attempt_token != claimed.attempt_token
        ):
            return
        job.status = JobStatus.queued
        job.worker_id = None
        job.attempt_token = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.available_at = _utcnow()
        job.payload_json = {
            **job_payload(job),
            "current_step": "queued",
            "message": "Проверка продолжится после запуска worker-а",
        }
        await session.commit()


async def _mark_failed_or_retry(
    claimed: ClaimedJob,
    exc: Exception,
    *,
    session_factory=AsyncSessionLocal,
) -> None:
    async with session_factory() as session:
        job = await session.get(BackgroundJob, claimed.job_id)
        if job is None or job.attempt_token != claimed.attempt_token:
            return
        job.retry_count = int(job.retry_count or 0) + 1
        job.error_message = str(exc)[:2000]
        retry = job.retry_count <= job.max_retries
        job.status = JobStatus.retrying if retry else JobStatus.failed
        job.completed_at = None if retry else _utcnow()
        job.available_at = (
            _utcnow() + timedelta(seconds=min(2 ** (job.retry_count - 1), 30))
            if retry
            else None
        )
        job.worker_id = None
        job.attempt_token = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        if not retry:
            job.deduplication_key = None
        job.payload_json = {
            **job_payload(job),
            "current_step": "retrying" if retry else "failed",
            "message": (
                "Временная ошибка. Повторяем незавершённую часть"
                if retry
                else "Не удалось завершить проверку"
            ),
        }
        await session.commit()


async def _heartbeat_loop(
    claimed: ClaimedJob,
    *,
    worker_id: str,
    stop: asyncio.Event,
    session_factory=AsyncSessionLocal,
    heartbeat_seconds: int | None = None,
    lease_seconds: int | None = None,
) -> None:
    interval = heartbeat_seconds or settings.ANALYSIS_JOB_HEARTBEAT_SECONDS
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            try:
                owned = await renew_job_lease(
                    claimed.job_id,
                    claimed.attempt_token,
                    worker_id=worker_id,
                    session_factory=session_factory,
                    lease_seconds=lease_seconds,
                )
            except Exception:  # noqa: BLE001
                # Краткая недоступность БД не передаёт владение сама по себе.
                # На следующем такте пробуем продлить снова; перед сохранением
                # результата attempt_token всё равно сверяется с БД.
                logger.exception(
                    "Не удалось обновить heartbeat фонового задания",
                    job_id=claimed.job_id,
                )
                continue
            if not owned:
                stop.set()
                return


async def execute_claimed_analysis_job(
    claimed: ClaimedJob,
    *,
    worker_id: str,
    session_factory=AsyncSessionLocal,
    heartbeat_seconds: int | None = None,
    lease_seconds: int | None = None,
) -> None:
    """Выполнить только ту попытку, которой worker ещё владеет."""

    heartbeat_stop = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_loop(
            claimed,
            worker_id=worker_id,
            stop=heartbeat_stop,
            session_factory=session_factory,
            heartbeat_seconds=heartbeat_seconds,
            lease_seconds=lease_seconds,
        ),
        name=f"full-analysis-heartbeat-{claimed.job_id}",
    )
    try:
        async with session_factory() as session:
            job = await session.get(BackgroundJob, claimed.job_id)
            if (
                job is None
                or job.status is not JobStatus.running
                or job.attempt_token != claimed.attempt_token
            ):
                raise JobLeaseLost(f"Задание {claimed.job_id} уже передано другому worker-у")

            payload = job_payload(job)
            application_id = int(payload["application_id"])
            requested_by_user_id = payload.get("requested_by_user_id")
            application = await session.get(TrademarkApplicationDraft, application_id)
            if application is None:
                raise LookupError("Заявка больше не существует")

            async def report(step: str, percent: int, message: str) -> None:
                await session.refresh(job)
                if job.attempt_token != claimed.attempt_token or heartbeat_stop.is_set():
                    raise JobLeaseLost(
                        f"Worker потерял аренду задания {claimed.job_id}"
                    )
                job.payload_json = {
                    **job_payload(job),
                    "progress": percent,
                    "current_step": step,
                    "message": message,
                }
                # Фазовый commit сохраняет и прогресс, и уже готовые результаты
                # анализа. После аварии worker повторяет только незавершённое.
                await session.commit()

            result = await run_full_analysis(
                session,
                application,
                llm_provider=get_llm_provider(),
                registry_provider=get_registry_provider(),
                user_id=int(requested_by_user_id) if requested_by_user_id else None,
                progress_callback=report,
                retry_incomplete_only=(
                    claimed.recovered
                    or bool(payload.get("retry_incomplete_only"))
                    or int(job.retry_count or 0) > 0
                ),
            )

            await session.refresh(job)
            if job.attempt_token != claimed.attempt_token or heartbeat_stop.is_set():
                raise JobLeaseLost(f"Итог задания {claimed.job_id} принадлежит другой попытке")
            job.status = JobStatus.completed
            job.result_json = result
            job.error_message = None
            job.completed_at = _utcnow()
            job.available_at = None
            job.worker_id = None
            job.attempt_token = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.deduplication_key = None
            job.payload_json = {
                **job_payload(job),
                "progress": 100,
                "current_step": "completed",
                "message": "Проверка завершена",
            }
            session.add(
                AuditLog(
                    user_id=(
                        int(requested_by_user_id) if requested_by_user_id else None
                    ),
                    application_id=application_id,
                    action="full_analysis.background.completed",
                    entity_type="BackgroundJob",
                    entity_id=str(job.id),
                    new_value_json={
                        "overall_risk": result.get("overall_risk"),
                        "verdict": result.get("verdict"),
                        "is_complete": result.get("is_complete"),
                        "worker_id": worker_id,
                    },
                )
            )
            await session.commit()
    except asyncio.CancelledError:
        await _release_interrupted_job(claimed, session_factory=session_factory)
        raise
    except JobLeaseLost:
        logger.warning("Попытка остановлена после потери аренды", job_id=claimed.job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Фоновый полный анализ завершился ошибкой", job_id=claimed.job_id)
        await _mark_failed_or_retry(claimed, exc, session_factory=session_factory)
    finally:
        heartbeat_stop.set()
        await asyncio.gather(heartbeat, return_exceptions=True)


class FullAnalysisWorker:
    """Один процесс worker-а с настраиваемой локальной конкурентностью."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        concurrency: int | None = None,
        poll_seconds: float | None = None,
        session_factory=AsyncSessionLocal,
        lease_seconds: int | None = None,
        heartbeat_seconds: int | None = None,
    ) -> None:
        self.worker_id = worker_id or default_worker_id()
        self.concurrency = max(1, concurrency or settings.ANALYSIS_WORKER_CONCURRENCY)
        self.poll_seconds = poll_seconds or settings.ANALYSIS_WORKER_POLL_SECONDS
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._running: set[asyncio.Task[None]] = set()

    def wake(self) -> None:
        self._wake.set()

    async def run(self) -> None:
        logger.info(
            "Worker полного анализа запущен",
            worker_id=self.worker_id,
            concurrency=self.concurrency,
        )
        try:
            while not self._stop.is_set():
                self._running = {task for task in self._running if not task.done()}
                while len(self._running) < self.concurrency:
                    claimed = await claim_next_analysis_job(
                        worker_id=self.worker_id,
                        session_factory=self.session_factory,
                        lease_seconds=self.lease_seconds,
                    )
                    if claimed is None:
                        break
                    task = asyncio.create_task(
                        execute_claimed_analysis_job(
                            claimed,
                            worker_id=self.worker_id,
                            session_factory=self.session_factory,
                            heartbeat_seconds=self.heartbeat_seconds,
                            lease_seconds=self.lease_seconds,
                        ),
                        name=f"full-analysis-{claimed.job_id}",
                    )
                    self._running.add(task)

                self._wake.clear()
                if self._running:
                    done, _ = await asyncio.wait(
                        self._running,
                        timeout=self.poll_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        await asyncio.gather(task, return_exceptions=True)
                else:
                    try:
                        await asyncio.wait_for(
                            self._wake.wait(), timeout=self.poll_seconds
                        )
                    except TimeoutError:
                        pass
        finally:
            tasks = list(self._running)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Worker полного анализа остановлен", worker_id=self.worker_id)

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()


_embedded_worker: FullAnalysisWorker | None = None
_embedded_task: asyncio.Task[None] | None = None


def schedule_analysis_job(_job_id: int) -> None:
    """Разбудить встроенный worker; внешний увидит строку при следующем poll."""

    if _embedded_worker is not None:
        _embedded_worker.wake()


async def resume_analysis_jobs() -> None:
    """Запустить встроенный worker только в локальном режиме."""

    global _embedded_task, _embedded_worker
    if settings.ANALYSIS_WORKER_MODE != "embedded":
        return
    if _embedded_task is not None and not _embedded_task.done():
        return
    _embedded_worker = FullAnalysisWorker(worker_id=f"embedded:{default_worker_id()}")
    _embedded_task = asyncio.create_task(
        _embedded_worker.run(), name="embedded-full-analysis-worker"
    )


async def stop_analysis_jobs() -> None:
    global _embedded_task, _embedded_worker
    if _embedded_worker is not None:
        await _embedded_worker.stop()
    if _embedded_task is not None:
        await asyncio.gather(_embedded_task, return_exceptions=True)
    _embedded_task = None
    _embedded_worker = None
