"""
API tests for the health check endpoint.

Verifies that the /api/v1/health endpoint:
- Returns HTTP 200
- Returns JSON with status="ok"
- Contains the application name and version fields
- The /health/detailed endpoint also succeeds (with DB dependency overridden)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_returns_200(self, client: TestClient):
        """The basic health endpoint must return HTTP 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client: TestClient):
        """Response body must contain status='ok'."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert body["status"] == "ok"

    def test_health_contains_app_name(self, client: TestClient):
        """Response body must contain the 'app' field."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert "app" in body
        assert len(body["app"]) > 0

    def test_health_contains_version(self, client: TestClient):
        """Response body must contain the 'version' field."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert "version" in body

    def test_health_content_type_is_json(self, client: TestClient):
        """Response Content-Type must be application/json."""
        response = client.get("/api/v1/health")
        assert "application/json" in response.headers.get("content-type", "")

    def test_health_detailed_returns_200(self, client: TestClient):
        """The detailed health endpoint must return HTTP 200 with in-memory DB."""
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200

    def test_health_detailed_contains_database_section(self, client: TestClient):
        """The detailed response must include a 'database' section."""
        response = client.get("/api/v1/health/detailed")
        body = response.json()
        assert "database" in body
        assert "ok" in body["database"]

    def test_health_detailed_database_ok_true(self, client: TestClient):
        """With in-memory DB, the database section should report ok=True."""
        response = client.get("/api/v1/health/detailed")
        body = response.json()
        assert body["database"]["ok"] is True

    def test_health_endpoint_method_not_allowed(self, client: TestClient):
        """POST to health endpoint should return 405 Method Not Allowed."""
        response = client.post("/api/v1/health")
        assert response.status_code == 405

    def test_health_is_publicly_accessible(self, client: TestClient):
        """Health endpoint must be accessible without authentication."""
        # No Authorization header
        response = client.get("/api/v1/health")
        assert response.status_code == 200
