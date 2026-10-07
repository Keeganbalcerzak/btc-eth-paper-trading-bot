from __future__ import annotations

from fastapi.testclient import TestClient

from bot.api import create_app


def test_api_health_and_metrics_endpoints():
    client = TestClient(create_app())

    health = client.get("/health")
    metrics = client.get("/metrics")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert metrics.status_code == 200
    assert "orders_submitted" in metrics.json()
