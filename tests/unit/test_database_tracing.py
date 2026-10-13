"""The database span hooks against in-memory SQLite. The asyncpg path, including that the
trace context survives SQLAlchemy's greenlet bridge, is covered by the integration test."""

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.tracing import TRACE_SPANS_KEY, attach_database_tracing, tracer


@pytest.fixture
def traced_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    with engine.connect():
        pass  # first connect runs dialect initialisation; keep that out of the spans
    attach_database_tracing(engine)
    yield engine
    engine.dispose()


def test_statements_inside_a_trace_become_client_spans(
    traced_engine: Engine, spans: InMemorySpanExporter
) -> None:
    with tracer.start_as_current_span("parent") as parent, traced_engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO t (id) VALUES (1)"))
        conn.execute(text("SELECT * FROM t"))

    finished = {span.name: span for span in spans.get_finished_spans()}
    parent_id = parent.get_span_context().span_id
    for operation in ("INSERT", "SELECT"):
        span = finished[operation]
        assert span.kind == SpanKind.CLIENT
        assert span.parent is not None
        assert span.parent.span_id == parent_id
        assert span.attributes["db.system.name"] == "sqlite"
        assert span.attributes["db.operation.name"] == operation
    assert "OTHER" in finished  # the CREATE TABLE


def test_the_statement_text_is_not_recorded(
    traced_engine: Engine, spans: InMemorySpanExporter
) -> None:
    with tracer.start_as_current_span("parent"), traced_engine.connect() as conn:
        conn.execute(text("SELECT 'sensitive-literal'"))

    span = next(s for s in spans.get_finished_spans() if s.name == "SELECT")
    assert "sensitive-literal" not in repr(dict(span.attributes))


def test_statements_outside_a_trace_get_no_span(
    traced_engine: Engine, spans: InMemorySpanExporter
) -> None:
    """A readiness probe or a migration should not create parentless root spans."""
    with traced_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    assert spans.get_finished_spans() == ()


def test_a_failed_statement_ends_its_span_as_an_error_without_leaking_its_text(
    traced_engine: Engine, spans: InMemorySpanExporter
) -> None:
    with tracer.start_as_current_span("parent"), traced_engine.connect() as conn:
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT * FROM table_that_does_not_exist"))
        conn.rollback()
        assert conn.info[TRACE_SPANS_KEY] == []  # nothing left open

    span = next(s for s in spans.get_finished_spans() if s.name == "SELECT")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "OperationalError"
    assert span.events == ()
    assert "table_that_does_not_exist" not in repr(dict(span.attributes)) + str(
        span.status.description
    )
