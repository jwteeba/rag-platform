"""Prometheus endpoint integration coverage."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, Settings
from rag_platform.main import create_app


def test_metrics_returns_prometheus_exposition() -> None:
    # `/metrics` is registered during app construction and does not need the
    # database/Redis lifespan, keeping this endpoint integration test hermetic.
    app = create_app(
        Settings(
            environment=Environment.TESTING,
            otel_enabled=False,
            prometheus_enabled=True,
        )
    )
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "rag_documents_uploaded_total" in response.text
