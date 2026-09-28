from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.exceptions import AppException
from app.main import create_app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    )


def _assert_error_shape(body: dict[str, dict[str, object]], code: str) -> None:
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code


async def test_unknown_route_uses_error_contract(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    _assert_error_shape(response.json(), "NOT_FOUND")


async def test_app_exception_uses_error_contract(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom-app")
    async def boom_app() -> None:
        raise AppException("Nope", code="TEAPOT", status_code=418)

    async with _client(app) as client:
        response = await client.get("/boom-app")
    assert response.status_code == 418
    _assert_error_shape(response.json(), "TEAPOT")
    assert response.json()["error"]["message"] == "Nope"


async def test_unexpected_exception_does_not_leak_details(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("SELECT * FROM secrets; password=hunter2")

    async with _client(app) as client:
        response = await client.get("/boom")
    assert response.status_code == 500
    _assert_error_shape(response.json(), "INTERNAL_ERROR")
    assert "hunter2" not in response.text
    assert "SELECT" not in response.text


async def test_validation_error_uses_error_contract(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/needs-int")
    async def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    async with _client(app) as client:
        response = await client.get("/needs-int", params={"n": "abc"})
    assert response.status_code == 422
    _assert_error_shape(response.json(), "VALIDATION_ERROR")
