from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"]
    assert payload["version"]


def test_health_returns_request_id_header():
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_health_echoes_incoming_request_id():
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_ready_endpoint_reports_integration_status_only():
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    checks = payload["checks"]
    for name in ("database", "object_storage", "identity", "ai_chat", "embeddings", "queue"):
        assert name in checks
        assert set(checks[name]) == {"configured", "verified"}


def test_ready_never_exposes_secret_material():
    response = client.get("/ready")
    body = response.text.lower()
    for forbidden in ("password", "secret", "token", "postgres://", "postgresql://"):
        assert forbidden not in body
