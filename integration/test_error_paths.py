"""Exercises every important error path through the full HTTP stack (spec section 6/7)."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.main import create_app

DB_URL = "postgresql+asyncpg://user:pw@127.0.0.1:5432/db"


async def _get(path: str, app: FastAPI) -> tuple[int, dict]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


async def test_authentication_exception_returns_401_with_www_authenticate(
    settings: Settings,
) -> None:
    app = create_app(settings)

    @app.get("/needs-auth")
    async def needs_auth() -> None:
        raise AuthenticationException()

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/needs-auth")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_authorization_exception_returns_403(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/needs-role")
    async def needs_role() -> None:
        raise AuthorizationException()

    status, body = await _get("/needs-role", app)
    assert status == 403
    assert body["error"]["code"] == "FORBIDDEN"


async def test_every_error_response_has_the_standard_shape(client: AsyncClient) -> None:
    for path in ("/does-not-exist", "/health/ready"):
        response = await client.get(path)
        if response.status_code < 400:
            continue
        body = response.json()
        assert set(body) == {"error"}
        assert set(body["error"]) == {"code", "message", "request_id"}
        assert isinstance(body["error"]["code"], str) and body["error"]["code"]
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
