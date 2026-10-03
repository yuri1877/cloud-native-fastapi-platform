"""Fixtures for tests that need a real PostgreSQL database.

Set TEST_DATABASE_URL to a dedicated database whose name ends in "_test"; the tests create
and drop tables in it. Without it, database-backed tests are skipped.
"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.database import Base, create_engine
from app.db.session import create_session_factory
from app.dependencies.auth import get_token_verifier
from tests.unit.auth_helpers import AUDIENCE, ISSUER, FakeTokenVerifier, make_token

OIDC_KWARGS = {
    "oidc_issuer": ISSUER,
    "oidc_audience": AUDIENCE,
    "oidc_jwks_url": "https://issuer.example.com/.well-known/jwks.json",
}


@pytest.fixture
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point at a database whose name ends with '_test'")
    return url


@pytest.fixture
def db_settings(test_database_url: str) -> Settings:
    return Settings(_env_file=None, app_env="test", database_url=test_database_url, **OIDC_KWARGS)


@pytest.fixture
async def db_engine(db_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(db_settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with create_session_factory(db_engine)() as session:
        yield session


@pytest.fixture
async def clean_engine(db_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Engine on a database with no tables (for migration tests)."""
    engine = create_engine(db_settings)

    async def _wipe() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    await _wipe()
    yield engine
    await _wipe()
    await engine.dispose()


@pytest.fixture
async def db_client(db_settings: Settings, db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """HTTP client wired to a real, migrated-schema test database, pre-authenticated as an
    admin (the highest role, so every RBAC-protected route in the CRUD test suites is
    reachable without each test having to manage its own token). Role-specific behaviour
    is covered separately in tests/integration/test_authorization.py."""
    from app.main import create_app

    app = create_app(db_settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    token = make_token(subject="admin-test-user", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
