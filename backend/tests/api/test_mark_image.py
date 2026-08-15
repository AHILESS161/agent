"""API изображения изобразительного и комбинированного обозначения."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.endpoints import documents
from app.infrastructure.database.models import (
    AnalysisKind,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    UserRole,
)
from app.services import file_storage
from app.services.mark_image import MarkImageResult
from app.services.visual_mark_similarity import cache_registry_image
from tests.conftest import login_headers


def _png(color: tuple[int, int, int] = (12, 158, 154)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (120, 80), color).save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(file_storage.settings, "FILE_STORAGE_PATH", str(tmp_path / "marks"))


@pytest.fixture
async def mark_case(client, api_user_factory, monkeypatch):
    await api_user_factory("mark-owner@test.ru", UserRole.client)
    headers = login_headers(client, "mark-owner@test.ru")
    owner = client.post(
        "/api/v1/clients",
        json={"type": "sole_proprietor", "full_name_or_company_name": "ИП Тест"},
        headers=headers,
    ).json()
    application = client.post(
        "/api/v1/applications",
        json={
            "client_id": owner["id"],
            "mark_name": "РЕГИСТР",
            "mark_type": "combined",
        },
        headers=headers,
    ).json()
    monkeypatch.setattr(
        documents,
        "process_mark_image",
        lambda content, filename: MarkImageResult(
            width=120,
            height=80,
            image_format="PNG",
            color_mode="RGB",
            dominant_colors=["#0C9E9A"],
            perceptual_hash="0123456789abcdef",
            recognized_text="РЕГИСТР",
            ocr_confidence=0.91,
            ocr_warning=None,
        ),
    )
    return headers, application["id"]


@pytest.mark.api
def test_upload_preview_and_detach_mark_image(client, mark_case):
    headers, application_id = mark_case
    uploaded = client.post(
        f"/api/v1/applications/{application_id}/mark-image",
        files={"file": ("logo.png", _png(), "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["recognized_text"] == "РЕГИСТР"
    assert body["width"] == 120
    assert body["visual_search_supported"] is False

    application = client.get(
        f"/api/v1/applications/{application_id}", headers=headers
    ).json()
    assert application["mark_image_file_id"] == str(body["document_id"])

    card = client.get(
        f"/api/v1/applications/{application_id}/mark-image", headers=headers
    )
    assert card.status_code == 200
    assert card.json()["recognized_text"] == "РЕГИСТР"

    preview = client.get(
        f"/api/v1/applications/{application_id}/mark-image/content", headers=headers
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/png")

    detached = client.delete(
        f"/api/v1/applications/{application_id}/mark-image", headers=headers
    )
    assert detached.status_code == 204
    assert client.get(
        f"/api/v1/applications/{application_id}/mark-image", headers=headers
    ).status_code == 404


@pytest.mark.api
def test_mark_image_rejects_pdf_and_word_mark(client, mark_case):
    headers, application_id = mark_case
    pdf = client.post(
        f"/api/v1/applications/{application_id}/mark-image",
        files={"file": ("not-a-logo.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        headers=headers,
    )
    assert pdf.status_code == 400

    client.put(
        f"/api/v1/applications/{application_id}",
        json={"mark_type": "word"},
        headers=headers,
    )
    wrong_type = client.post(
        f"/api/v1/applications/{application_id}/mark-image",
        files={"file": ("logo.png", _png(), "image/png")},
        headers=headers,
    )
    assert wrong_type.status_code == 409


@pytest.mark.api
def test_mark_image_requires_authorization(client, mark_case):
    _, application_id = mark_case
    assert client.get(
        f"/api/v1/applications/{application_id}/mark-image"
    ).status_code == 401


@pytest.mark.api
async def test_registry_match_image_is_served_from_protected_cache(
    client, mark_case, async_engine
):
    headers, application_id = mark_case
    cache_key = cache_registry_image(_png(), "image/png")
    factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        assessment = RiskAssessment(
            application_id=application_id,
            analysis_kind=AnalysisKind.relative_grounds,
        )
        session.add(assessment)
        await session.flush()
        finding = RiskFinding(
            assessment_id=assessment.id,
            category="conflicting_mark",
            level=RiskLevel.medium,
            explanation="Визуально похожая карточка",
            verification_json={
                "image_comparison": {
                    "cache_key": cache_key,
                    "mime_type": "image/png",
                    "score": 0.8,
                }
            },
        )
        session.add(finding)
        await session.commit()
        finding_id = finding.id

    assert client.get(
        f"/api/v1/risk-findings/{finding_id}/registry-image"
    ).status_code == 401
    response = client.get(
        f"/api/v1/risk-findings/{finding_id}/registry-image", headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
