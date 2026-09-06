from __future__ import annotations

import io
import json
import time
import zipfile

import pytest
from sqlalchemy import text

from app.core.config import Settings, settings
from app.services.file_storage import FileValidationError, validate_upload
from app.api.middleware.rate_limit import RateLimiter, Rule
from app.workers.health import check_worker, publish_heartbeat


@pytest.mark.parametrize("secret", ["", "a" * 64, "replace-with-at-least-64-random-hex-characters",
                                    "change-me-in-production-use-secrets-token-hex-32"])
def test_server_rejects_placeholder_without_disclosing_input(secret):
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=secret, DEBUG=False)
    assert "input_value" not in str(caught.value)
    if secret:
        assert secret not in str(caught.value)


def test_server_accepts_separate_key_and_csv_origins():
    config = Settings(_env_file=None, ENVIRONMENT="production", DEBUG=False,
                      SECRET_KEY="0123456789abcdef" * 4, CORS_ORIGINS="https://a.test,https://b.test")
    assert config.CORS_ORIGINS == ["https://a.test", "https://b.test"]


def test_limiter_expires_abandoned_keys_and_does_not_evict_active_keys():
    limiter = RateLimiter(max_keys=2)
    rule = Rule(1, 60)
    assert limiter.check("a", rule, 0)[0]
    assert limiter.check("b", rule, 0)[0]
    assert not limiter.check("c", rule, 1)[0]
    assert not limiter.check("a", rule, 2)[0]
    assert limiter.check("c", rule, 63)[0]
    assert len(limiter._hits) == 1


def test_docx_requires_real_archive_and_bounded_expansion():
    with pytest.raises(FileValidationError):
        validate_upload(b"PK\x03\x04garbage", "fake.docx")
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ["word/document.xml", "[Content_Types].xml", "_rels/.rels"]:
            archive.writestr(name, b"a" * 100000)
    with pytest.raises(FileValidationError):
        validate_upload(content.getvalue(), "bomb.docx")


def test_worker_readiness_detects_stale_or_missing_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "health.json"
    monkeypatch.setattr(settings, "WORKER_HEARTBEAT_PATH", str(path))
    assert not check_worker()[0]
    publish_heartbeat("worker-test")
    assert check_worker()[0]
    path.write_text(json.dumps({"worker_id": "test", "time": time.time() - 3600}))
    assert not check_worker()[0]


@pytest.mark.asyncio
async def test_schema_checks_exact_migration_heads(async_engine, monkeypatch):
    from pathlib import Path
    from alembic.script import ScriptDirectory
    from app.infrastructure.database import session as module
    monkeypatch.setattr(module, "engine", async_engine)
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        await connection.execute(text("INSERT INTO alembic_version VALUES ('old')"))
    assert not (await module.check_schema())[0]
    heads = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "migrations")).get_heads()
    async with async_engine.begin() as connection:
        await connection.execute(text("DELETE FROM alembic_version"))
        for head in heads:
            await connection.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": head})
    assert (await module.check_schema())[0]


@pytest.mark.asyncio
async def test_sandbox_extracts_text_outside_api_process(monkeypatch):
    from app.services.document_sandbox import extract_text
    monkeypatch.setattr(settings, "OCR_ENABLED", False)
    assert "hello" in await extract_text(b"hello from sandbox", "test.txt")


def test_long_and_unicode_passwords_use_the_entire_input():
    from app.core.security import hash_password, verify_password
    for prefix in ("a" * 72, "пароль" * 20):
        hashed = hash_password(prefix + "one")
        assert verify_password(prefix + "one", hashed)
        assert not verify_password(prefix + "two", hashed)


@pytest.mark.asyncio
async def test_budget_is_persistent_and_failed_reservation_is_atomic(async_session, async_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from fastapi import HTTPException
    from app.services.resource_limits import reserve_llm_budget
    from app.infrastructure.database.models import ResourceBudget
    from sqlalchemy import select
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "LLM_DAILY_USER_BUDGET", 10)
    monkeypatch.setattr(settings, "LLM_DAILY_GLOBAL_BUDGET", 15)
    await reserve_llm_budget(8, 1, factory)
    with pytest.raises(HTTPException):
        await reserve_llm_budget(3, 1, factory)
    await reserve_llm_budget(7, 2, factory)
    with pytest.raises(HTTPException):
        await reserve_llm_budget(1, 3, factory)
    async with factory() as session:
        rows = list((await session.scalars(select(ResourceBudget))).all())
        assert sorted(row.spent for row in rows) == [7, 8, 15]


@pytest.mark.asyncio
async def test_document_deletion_rollback_preserves_original(async_session, tmp_path, monkeypatch):
    from app.infrastructure.database.models import SourceDocument, SourceChannel
    from app.services.file_storage import save_upload, read_file
    from app.services.document_lifecycle import delete_document_and_release_blob
    monkeypatch.setattr(settings, "FILE_STORAGE_PATH", str(tmp_path))
    original = b"Synthetic rollback document"
    stored = save_upload(original, "rollback.txt")
    document = SourceDocument(original_filename="rollback.txt", stored_path=stored.stored_path,
        file_size=stored.size, sha256=stored.sha256, detected_mime=stored.detected_mime,
        source_channel=SourceChannel.manual_upload)
    async_session.add(document)
    await async_session.commit()
    document_id = document.id
    await delete_document_and_release_blob(async_session, document)
    await async_session.rollback()
    assert await async_session.get(SourceDocument, document_id) is not None
    assert read_file(stored.stored_path) == original
