from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


async def test_docs_disabled_in_prod() -> None:
    app = create_app(Settings(_env_file=None, app_env="prod"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404
        assert (await client.get("/health/live")).status_code == 200
