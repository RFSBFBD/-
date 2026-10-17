from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_exception_handlers


def build_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/needs-id")
    async def needs_id(item_id: int):  # noqa: ANN001
        return {"item_id": item_id}

    return test_app


client = TestClient(build_app())


def test_not_found_is_normalized():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "http_error"
    assert error["request_id"]


def test_validation_error_is_normalized():
    response = client.get("/needs-id")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["type"] == "validation_error"
    assert error["details"]
    assert "request_id" in error


def test_unhandled_exception_is_not_leaked():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/boom")
    async def boom():
        raise RuntimeError("internal detail should not leak")

    failing = TestClient(test_app, raise_server_exceptions=False)
    response = failing.get("/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["type"] == "internal_error"
    assert "internal detail" not in response.text
