"""Конкурентность, lease recovery и идемпотентность фонового worker-а."""

from __future__ import annotations

import asyncio
import multiprocessing
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.models import (
    AuditLog,
    BackgroundJob,
    Client,
    ClientType,
    JobStatus,
    MarkType,
    TrademarkApplicationDraft,
)
from app.infrastructure.database.session import Base
from app.services.full_analysis_jobs import (
    FULL_ANALYSIS_JOB_TYPE,
    ClaimedJob,
    FullAnalysisWorker,
    _release_interrupted_job,
    claim_next_analysis_job,
    execute_claimed_analysis_job,
    job_deduplication_key,
    renew_job_lease,
)


def _claim_from_os_process(database_path: str, worker_id: str, output) -> None:
    """Отдельная process entry point; должна оставаться на уровне модуля."""

    async def run() -> None:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{database_path}",
            connect_args={"timeout": 30},
        )
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            claim = await claim_next_analysis_job(
                worker_id=worker_id,
                session_factory=factory,
                lease_seconds=30,
            )
            output.put(claim.job_id if claim else None)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest_asyncio.fixture
async def worker_db(tmp_path):
    path = (tmp_path / "worker.sqlite3").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        connect_args={"timeout": 30},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _enqueue(factory, number: int, *, status=JobStatus.queued) -> int:
    async with factory() as session:
        job = BackgroundJob(
            job_type=FULL_ANALYSIS_JOB_TYPE,
            status=status,
            payload_json={"application_id": number},
            deduplication_key=job_deduplication_key(number),
        )
        session.add(job)
        await session.commit()
        return job.id


@pytest.mark.asyncio
async def test_two_workers_cannot_claim_the_same_job(worker_db):
    job_id = await _enqueue(worker_db, 1)

    first, second = await asyncio.gather(
        claim_next_analysis_job(worker_id="worker-a", session_factory=worker_db),
        claim_next_analysis_job(worker_id="worker-b", session_factory=worker_db),
    )

    claims = [claim for claim in (first, second) if claim is not None]
    assert len(claims) == 1
    assert claims[0].job_id == job_id


@pytest.mark.asyncio
async def test_eight_os_processes_claim_one_job_only_once(tmp_path):
    path = (tmp_path / "multiprocess-worker.sqlite3").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", connect_args={"timeout": 30}
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    job_id = await _enqueue(factory, 999)
    await engine.dispose()

    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    processes = [
        context.Process(
            target=_claim_from_os_process,
            args=(path, f"process-{number}", output),
        )
        for number in range(8)
    ]
    for process in processes:
        process.start()
    for process in processes:
        await asyncio.to_thread(process.join, 30)
        assert process.exitcode == 0

    results = [output.get(timeout=2) for _ in processes]
    assert results.count(job_id) == 1
    assert results.count(None) == 7


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_with_new_attempt_token(worker_db):
    job_id = await _enqueue(worker_db, 2, status=JobStatus.running)
    async with worker_db() as session:
        job = await session.get(BackgroundJob, job_id)
        job.worker_id = "dead-worker"
        job.attempt_token = "old-token"
        job.heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=4)
        await session.commit()

    claim = await claim_next_analysis_job(
        worker_id="replacement", session_factory=worker_db
    )

    assert claim is not None
    assert claim.recovered is True
    assert claim.attempt_token != "old-token"
    async with worker_db() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.worker_id == "replacement"
        assert job.payload_json["recovered_from_expired_lease"] is True


@pytest.mark.asyncio
async def test_stale_worker_cannot_release_reclaimed_job(worker_db):
    job_id = await _enqueue(worker_db, 3, status=JobStatus.running)
    async with worker_db() as session:
        job = await session.get(BackgroundJob, job_id)
        job.worker_id = "old"
        job.attempt_token = "old-token"
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    replacement = await claim_next_analysis_job(
        worker_id="new", session_factory=worker_db
    )
    assert replacement is not None

    await _release_interrupted_job(
        ClaimedJob(job_id, "old-token", recovered=False),
        session_factory=worker_db,
    )

    async with worker_db() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status is JobStatus.running
        assert job.worker_id == "new"
        assert job.attempt_token == replacement.attempt_token


@pytest.mark.asyncio
async def test_heartbeat_extends_only_current_lease(worker_db):
    await _enqueue(worker_db, 4)
    claim = await claim_next_analysis_job(
        worker_id="worker", session_factory=worker_db, lease_seconds=5
    )
    assert claim is not None
    async with worker_db() as session:
        before = (await session.get(BackgroundJob, claim.job_id)).lease_expires_at

    assert await renew_job_lease(
        claim.job_id,
        claim.attempt_token,
        worker_id="worker",
        session_factory=worker_db,
        lease_seconds=30,
    )
    assert not await renew_job_lease(
        claim.job_id,
        "stale-token",
        worker_id="worker",
        session_factory=worker_db,
        lease_seconds=30,
    )
    async with worker_db() as session:
        after = (await session.get(BackgroundJob, claim.job_id)).lease_expires_at
    assert after > before


@pytest.mark.asyncio
async def test_completed_attempt_releases_deduplication_key(
    worker_db, monkeypatch
):
    async with worker_db() as session:
        applicant = Client(
            full_name_or_company_name='ООО "WORKER"',
            type=ClientType.company,
            inn="7707083893",
        )
        session.add(applicant)
        await session.flush()
        application = TrademarkApplicationDraft(
            client_id=applicant.id,
            mark_name="WORKER",
            mark_text="WORKER",
            mark_type=MarkType.word,
        )
        session.add(application)
        await session.commit()
        application_id = application.id

    job_id = await _enqueue(worker_db, application_id)
    claim = await claim_next_analysis_job(
        worker_id="executor", session_factory=worker_db
    )
    assert claim is not None and claim.job_id == job_id

    async def fake_analysis(_session, _application, **kwargs):
        await kwargs["progress_callback"]("relative_grounds", 60, "Ищем знаки")
        return {
            "overall_risk": "low",
            "verdict": "proceed",
            "is_complete": True,
        }

    monkeypatch.setattr(
        "app.services.full_analysis_jobs.run_full_analysis", fake_analysis
    )
    monkeypatch.setattr(
        "app.services.full_analysis_jobs.get_llm_provider", lambda: object()
    )
    monkeypatch.setattr(
        "app.services.full_analysis_jobs.get_registry_provider", lambda: object()
    )

    await execute_claimed_analysis_job(
        claim,
        worker_id="executor",
        session_factory=worker_db,
        heartbeat_seconds=60,
    )

    async with worker_db() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status is JobStatus.completed
        assert job.deduplication_key is None
        assert job.attempt_token is None
        assert job.result_json["verdict"] == "proceed"
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "BackgroundJob",
                    AuditLog.entity_id == str(job_id),
                )
            )
        ).scalar_one()
        assert audit.action == "full_analysis.background.completed"


@pytest.mark.asyncio
async def test_eight_workers_claim_hundred_jobs_without_duplicates(worker_db):
    for number in range(100, 200):
        await _enqueue(worker_db, number)

    async def drain(worker_number: int) -> list[int]:
        claimed: list[int] = []
        while True:
            item = await claim_next_analysis_job(
                worker_id=f"load-{worker_number}", session_factory=worker_db
            )
            if item is None:
                return claimed
            claimed.append(item.job_id)

    batches = await asyncio.gather(*(drain(number) for number in range(8)))
    ids = [job_id for batch in batches for job_id in batch]

    assert len(ids) == 100
    assert len(set(ids)) == 100
    async with worker_db() as session:
        running = list(
            (
                await session.execute(
                    select(BackgroundJob).where(
                        BackgroundJob.status == JobStatus.running
                    )
                )
            ).scalars()
        )
    assert len(running) == 100


@pytest.mark.asyncio
async def test_idle_worker_stops_gracefully(worker_db):
    worker = FullAnalysisWorker(
        worker_id="graceful",
        session_factory=worker_db,
        poll_seconds=0.01,
    )
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.03)
    await worker.stop()

    await asyncio.wait_for(task, timeout=1)
