"""API tests for the liveness and readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rag_platform.core.middleware.request_id import REQUEST_ID_HEADER


class TestLiveness:
    def test_returns_200_ok(self, client: TestClient) -> None:
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_response_carries_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health/live")

        assert REQUEST_ID_HEADER in response.headers
        assert len(response.headers[REQUEST_ID_HEADER]) > 0

    def test_echoes_client_supplied_request_id(self, client: TestClient) -> None:
        response = client.get("/health/live", headers={REQUEST_ID_HEADER: "test-request-id-123"})

        assert response.headers[REQUEST_ID_HEADER] == "test-request-id-123"


class TestReadiness:
    def test_returns_200_ok_with_version(self, client: TestClient) -> None:
        response = client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
