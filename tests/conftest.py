import io
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.core.tracing import configure_tracing
from app.db.database import Base, create_engine
from app.db.session import create_session_factory
from app.dependencies.auth import get_token_verifier
from app.main import create_app
from tests.unit.auth_helpers import AUDIENCE, ISSUER, FakeTokenVerifier, make_token

OIDC_KWARGS = {
    "oidc_issuer": ISSUER,
    "oidc_audience": AUDIENCE,
    "oidc_jwks_url": "https://issuer.example.com/.well-known/jwks.json",
}


# --- application ------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- logs and traces --------------------------------------------------------------------


@pytest.fixture
def json_logs() -> Iterator[Callable[[], list[dict[str, Any]]]]:
    """Everything logged during a test, formatted exactly as in production and parsed back
    into dicts. Yields a function that returns the lines logged so far."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test-service", "test"))

    root = logging.getLogger()
    previous_root_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # httpx logs every request URL (query string included) at INFO. That is the test
    # client's own noise, not application output, so keep it out of what we assert on.
    client_loggers = [logging.getLogger(name) for name in ("httpx", "httpcore")]
    previous_levels = [logger.level for logger in client_loggers]
    for logger in client_loggers:
        logger.setLevel(logging.WARNING)

    def read() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    try:
        yield read
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_root_level)
        for logger, level in zip(client_loggers, previous_levels, strict=True):
            logger.setLevel(level)


@pytest.fixture(scope="session")
def span_exporter() -> InMemorySpanExporter:
    """Collects every finished span. The tracer provider is process-wide and already exists
    (importing app.main created it), so the exporter is attached to it once, not per test."""
    exporter = InMemorySpanExporter()
    provider = configure_tracing(Settings(_env_file=None, app_env="test"))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


@pytest.fixture
def spans(span_exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    """The finished spans of the current test (`spans.get_finished_spans()`)."""
    span_exporter.clear()
    yield span_exporter
    span_exporter.clear()


# --- a real PostgreSQL database ---------------------------------------------------------
# Set TEST_DATABASE_URL to a dedicated database whose name ends in "_test"; the tests create
# and drop tables in it. Without it, every test that uses these fixtures is skipped.
# They live here, not in tests/integration, so the contract and end-to-end tests can use them.


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
    app = create_app(db_settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    token = make_token(subject="admin-test-user", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
