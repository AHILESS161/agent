import pytest
from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.mark.asyncio
async def test_foreign_case_routes_are_denied_before_processing(client, api_user_factory):
    for name, role in (("owner", UserRole.client), ("other", UserRole.client), ("lawyer", UserRole.lawyer)):
        await api_user_factory(f"{name}@example.com", role)
    owner = login_headers(client, "owner@example.com")
    applicant = client.post("/api/v1/clients", headers=owner,
        json={"type": "individual", "full_name_or_company_name": "Synthetic owner"}).json()
    app = client.post("/api/v1/applications", headers=owner,
        json={"client_id": applicant["id"], "mark_name": "SYNTHETIC", "mark_type": "word"}).json()
    root = f"/api/v1/applications/{app['id']}"
    for email in ("other@example.com", "lawyer@example.com"):
        headers = login_headers(client, email)
        for suffix in ("", "/risk-analysis", "/risk-analysis/history", "/risk-report",
                       "/documents", "/status", "/conflicts", "/legal-review"):
            response = client.get(root + suffix, headers=headers)
            assert response.status_code == 403, (suffix, response.text)
        for suffix, body in (("/transition", {"new_status": "closed", "expected_status": "draft"}),
                             ("/mvp-run", {}), ("/full-analysis/jobs", {})):
            response = client.post(root + suffix, headers=headers, json=body)
            assert response.status_code == 403, (suffix, response.text)
    assert client.get(root, headers=owner).json()["status"] == "draft"
    denied = client.post("/api/v1/applications", headers=login_headers(client, "other@example.com"),
                         json={"client_id": applicant["id"]})
    assert denied.status_code == 403
    assert client.put(root, headers=owner, json={"assigned_lawyer_id": 2}).status_code == 403
    assert client.post(root + "/transition", headers=owner,
        json={"new_status": "submitted", "expected_status": "draft"}).status_code == 409
    assert client.post(root + "/transition", headers=owner,
        json={"new_status": "closed", "expected_status": "info_received"}).status_code == 409


@pytest.mark.asyncio
async def test_password_change_and_logout_revoke_all_prior_tokens(client, api_user_factory):
    await api_user_factory("session@example.com", UserRole.client)
    first = login_headers(client, "session@example.com")
    second = login_headers(client, "session@example.com")
    response = client.post("/api/v1/auth/change-password", headers=first,
        json={"current_password": "test12345", "new_password": "long-new-password-12345"})
    assert response.status_code == 204, response.text
    for headers in (first, second):
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    fresh = login_headers(client, "session@example.com", "long-new-password-12345")
    assert client.post("/api/v1/auth/logout-all", headers=fresh).status_code == 204
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 401
