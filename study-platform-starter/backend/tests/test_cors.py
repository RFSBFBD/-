from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_allowed_origin_receives_cors_header():
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_disallowed_origin_receives_no_cors_header():
    response = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_request_id_header_is_exposed():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-request-id" in allow_headers
