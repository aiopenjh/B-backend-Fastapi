import httpx
import pytest
from fastapi import FastAPI

from common.middleware import register_middleware
from common.schemas import APIResponse


@pytest.fixture
def client() -> httpx.AsyncClient:
    app = FastAPI()
    register_middleware(app)

    @app.get("/ping", response_model=APIResponse[dict])
    async def ping():
        return APIResponse.ok({"pong": True})

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


async def test_response_body_request_id_matches_header(client):
    async with client:
        response = await client.get("/ping")

    request_id = response.headers["X-Request-ID"]
    assert request_id
    assert response.json()["request_id"] == request_id


async def test_each_request_gets_its_own_request_id(client):
    async with client:
        first = await client.get("/ping")
        second = await client.get("/ping")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_unhandled_error_returns_500_envelope_with_request_id(client):
    async with client:
        response = await client.get("/boom")

    request_id = response.headers.get("X-Request-ID")
    body = response.json()
    assert response.status_code == 500
    assert request_id
    assert body["success"] is False
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["request_id"] == request_id


async def test_cors_response_exposes_request_id_header(client):
    async with client:
        response = await client.get(
            "/ping", headers={"Origin": "http://localhost:3000"}
        )

    exposed = response.headers.get("access-control-expose-headers", "")
    assert "x-request-id" in exposed.lower()
