import io
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.core.tracing import configure_tracing
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


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
