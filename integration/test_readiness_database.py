from typing import Annotated

from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.dependencies.db import get_session
from app.main import create_app

UNREACHABLE_URL = "postgresql+asyncpg://user:secret-pw@127.0.0.1:1/nodb"


def _client(settings: Settings) -> tuple[AsyncClient, object]:
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test"), app


async def test_readiness_fails_when_database_unreachable() -> None:
    settings = Settings(_env_file=None, app_env="test", database_url=UNREACHABLE_URL)
    client, _ = _client(settings)
    async with client:
        response = await client.get("/health/ready")
        live = await client.get("/health/live")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_READY"
    assert "secret-pw" not in response.text
    # Liveness must not depend on the database.
    assert live.status_code == 200


async def test_readiness_ok_with_database(db_settings: Settings) -> None:
    client, _ = _client(db_settings)
    async with client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_get_session_returns_503_when_database_not_configured(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/needs-db")
    async def needs_db(session: Annotated[AsyncSession, Depends(get_session)]) -> None:
        return None

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/needs-db")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
