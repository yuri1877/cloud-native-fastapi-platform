"""Shared setup for the end-to-end tests. Not a test file."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.dependencies.auth import get_token_verifier
from app.main import create_app
from tests.unit.auth_helpers import FakeTokenVerifier, make_token


@asynccontextmanager
async def admin_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """The real application, authenticated as an admin through a fake JWKS client."""
    app = create_app(settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    headers = {"Authorization": f"Bearer {make_token(subject='e2e-admin', roles=['admin'])}"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
