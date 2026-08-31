"""Прогресс клиентской карточки определяется по фактическим артефактам дела."""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def lawyer_auth(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("client-progress@test.ru", UserRole.lawyer)
    return login_headers(client, "client-progress@test.ru")


def _create_application(client, headers: dict[str, str]) -> int:
    applicant = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": 'ООО "Прогресс"'},
        headers=headers,
    )
    assert applicant.status_code == 201, applicant.text
    application = client.post(
        "/api/v1/applications",
        json={"client_id": applicant.json()["id"], "mark_name": "ПРОГРЕСС"},
        headers=headers,
    )
    assert application.status_code == 201, application.text
    return application.json()["id"]


def _listed_step(client, headers: dict[str, str], application_id: int) -> int:
    response = client.get("/api/v1/applications", headers=headers)
    assert response.status_code == 200, response.text
    item = next(row for row in response.json()["items"] if row["id"] == application_id)
    return item["client_progress_step"]


@pytest.mark.api
def test_progress_uses_classes_and_analysis_job_even_while_status_is_draft(
    client, lawyer_auth
):
    application_id = _create_application(client, lawyer_auth)
    assert _listed_step(client, lawyer_auth, application_id) == 1

    added_class = client.post(
        f"/api/v1/applications/{application_id}/classes",
        json={"class_number": 37},
        headers=lawyer_auth,
    )
    assert added_class.status_code == 201, added_class.text
    assert _listed_step(client, lawyer_auth, application_id) == 2

    queued = client.post(
        f"/api/v1/applications/{application_id}/full-analysis/jobs",
        headers=lawyer_auth,
    )
    assert queued.status_code == 202, queued.text
    assert _listed_step(client, lawyer_auth, application_id) == 3

