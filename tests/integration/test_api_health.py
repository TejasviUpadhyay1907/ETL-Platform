"""
Integration tests for health check endpoints.

These tests verify the application starts successfully and all health
endpoints return the expected responses. They are the first integration
tests added and serve as a baseline for confirming the infrastructure works.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestPingEndpoint:
    """Tests for GET /api/v1/health/ping"""

    def test_ping_returns_200(self, client: TestClient):
        """Ping endpoint must return 200 OK."""
        response = client.get("/api/v1/health/ping")
        assert response.status_code == 200

    def test_ping_returns_pong(self, client: TestClient):
        """Ping response must contain 'pong'."""
        response = client.get("/api/v1/health/ping")
        data = response.json()
        assert data["ping"] == "pong"

    def test_ping_has_timestamp(self, client: TestClient):
        """Ping response must include a timestamp."""
        response = client.get("/api/v1/health/ping")
        data = response.json()
        assert "timestamp" in data


@pytest.mark.integration
class TestVersionEndpoint:
    """Tests for GET /api/v1/health/version"""

    def test_version_returns_200(self, client: TestClient):
        """Version endpoint returns 200."""
        response = client.get("/api/v1/health/version")
        assert response.status_code == 200

    def test_version_response_structure(self, client: TestClient):
        """Version response has expected fields."""
        response = client.get("/api/v1/health/version")
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert data["data"]["app_name"] == "ETL Platform"
        assert data["data"]["version"] is not None
        assert data["data"]["environment"] is not None

    def test_version_includes_meta(self, client: TestClient):
        """Response envelope includes meta block."""
        response = client.get("/api/v1/health/version")
        data = response.json()
        assert "meta" in data
        assert "timestamp" in data["meta"]


@pytest.mark.integration
class TestLivenessEndpoint:
    """Tests for GET /api/v1/health/live"""

    def test_liveness_returns_200(self, client: TestClient):
        """Liveness endpoint returns 200."""
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200

    def test_liveness_confirms_alive(self, client: TestClient):
        """Liveness response confirms application is alive."""
        response = client.get("/api/v1/health/live")
        data = response.json()
        assert data["alive"] is True


@pytest.mark.integration
class TestHealthEndpoint:
    """Tests for GET /api/v1/health"""

    def test_health_returns_2xx(self, client: TestClient):
        """Health endpoint returns a 2xx or 503 depending on DB state."""
        response = client.get("/api/v1/health")
        assert response.status_code in (200, 503)

    def test_health_response_has_status_field(self, client: TestClient):
        """Health response always includes a status field."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "data" in data
        assert "status" in data["data"]

    def test_health_status_is_known_value(self, client: TestClient):
        """Health status is one of the expected values."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["data"]["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_includes_uptime(self, client: TestClient):
        """Health response includes uptime."""
        response = client.get("/api/v1/health")
        data = response.json()
        # Uptime may be None if db is down, but field should be present
        assert "uptime_seconds" in data["data"]


@pytest.mark.integration
class TestResponseHeaders:
    """Tests for standard response headers set by middleware."""

    def test_request_id_header_present(self, client: TestClient):
        """All responses include X-Request-ID header."""
        response = client.get("/api/v1/health/ping")
        assert "x-request-id" in response.headers

    def test_process_time_header_present(self, client: TestClient):
        """All responses include X-Process-Time-Ms header."""
        response = client.get("/api/v1/health/ping")
        assert "x-process-time-ms" in response.headers

    def test_security_headers_present(self, client: TestClient):
        """Security headers are present on all responses."""
        response = client.get("/api/v1/health/ping")
        assert "x-content-type-options" in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_request_id_echoed_back(self, client: TestClient):
        """Client-provided X-Request-ID is echoed in response."""
        custom_id = "my-custom-trace-id-12345"
        response = client.get(
            "/api/v1/health/ping",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers.get("x-request-id") == custom_id


@pytest.mark.integration
class TestNotFoundHandling:
    """Tests for 404 error handling.

    Note: With JWT auth middleware active, unauthenticated requests to unknown
    paths receive 401 (authentication required) rather than 404. To get a 404,
    the request must be authenticated. Health paths are public and still 404.
    """

    def test_unknown_public_path_returns_404(self, client: TestClient):
        """Requests to unknown sub-paths under /api/v1/health return 404 (public path)."""
        response = client.get("/api/v1/health/this-does-not-exist-xyz")
        assert response.status_code == 404

    def test_unknown_path_unauthenticated_returns_401(self, client: TestClient):
        """Unauthenticated requests to unknown protected paths return 401."""
        response = client.get("/api/v1/nonexistent-path")
        assert response.status_code == 401

    def test_404_uses_standard_envelope(self, client: TestClient):
        """404 responses under public paths use the standard error envelope."""
        response = client.get("/api/v1/health/this-does-not-exist-xyz")
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "data" in data
        assert "meta" in data
