"""Tracing through the real HTTP stack: server spans, trust in inbound context, log
correlation, and (with TEST_DATABASE_URL) service and database spans nested under a request."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app.core.config import Settings
from app.core.request_context import REQUEST_ID_HEADER
from app.main import create_app

LogReader = Callable[[], list[dict[str, Any]]]

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


def _server_spans(spans: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in spans.get_finished_spans() if s.kind == SpanKind.SERVER]


def _app_with_boom_route(settings: Settings) -> Any:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("cannot connect with password hunter2")

    return app


async def test_a_request_becomes_a_server_span(
    client: AsyncClient, spans: InMemorySpanExporter
) -> None:
    user_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/users/{user_id}", headers={REQUEST_ID_HEADER: "trace-test-0001"}
    )

    [span] = _server_spans(spans)
    assert span.name == "GET /api/v1/users/{user_id}"
    assert span.attributes["http.route"] == "/api/v1/users/{user_id}"
    assert span.attributes["url.path"] == f"/api/v1/users/{user_id}"
    assert span.attributes["http.request.method"] == "GET"
    assert span.attributes["http.response.status_code"] == response.status_code
    assert span.attributes["app.request_id"] == "trace-test-0001"
    assert span.parent is None


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/metrics"])
async def test_probes_and_scrapes_are_not_traced(
    client: AsyncClient, spans: InMemorySpanExporter, path: str
) -> None:
    await client.get(path)

    assert spans.get_finished_spans() == ()


async def test_an_unmatched_request_is_named_by_its_method_only(
    client: AsyncClient, spans: InMemorySpanExporter
) -> None:
    await client.get("/no/such/route")

    [span] = _server_spans(spans)
    assert span.name == "GET"
    assert "http.route" not in span.attributes
    assert span.attributes["http.response.status_code"] == 404
    assert span.status.status_code == StatusCode.UNSET  # a 404 is not a server fault


async def test_an_unrecognised_method_cannot_create_new_span_names(
    client: AsyncClient, spans: InMemorySpanExporter
) -> None:
    await client.request("BREW", "/api/v1/me")

    [span] = _server_spans(spans)
    assert span.attributes["http.request.method"] == "_OTHER"
    assert span.name.startswith("_OTHER")
    assert "BREW" not in span.name


async def test_an_unhandled_exception_records_the_error_type_and_never_the_message(
    settings: Settings, spans: InMemorySpanExporter
) -> None:
    transport = ASGITransport(app=_app_with_boom_route(settings), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    [span] = _server_spans(spans)
    assert span.name == "GET /boom"
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.attributes["http.response.status_code"] == 500
    assert span.events == ()
    assert "hunter2" not in repr(dict(span.attributes)) + str(span.status.description)


async def test_an_inbound_traceparent_is_ignored_by_default(
    client: AsyncClient, spans: InMemorySpanExporter
) -> None:
    await client.get("/no/such/route", headers={"traceparent": TRACEPARENT})

    [span] = _server_spans(spans)
    assert span.parent is None
    assert format(span.context.trace_id, "032x") != TRACE_ID


async def test_an_inbound_traceparent_is_continued_when_trusted(
    spans: InMemorySpanExporter,
) -> None:
    app = create_app(Settings(_env_file=None, app_env="test", tracing_trust_inbound_context=True))
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/no/such/route", headers={"traceparent": TRACEPARENT})

    [span] = _server_spans(spans)
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert span.parent is not None
    assert format(span.parent.span_id, "016x") == PARENT_SPAN_ID


async def test_the_access_log_carries_the_trace_and_span_ids(
    client: AsyncClient, spans: InMemorySpanExporter, json_logs: LogReader
) -> None:
    await client.get("/no/such/route")

    [span] = _server_spans(spans)
    [access] = [line for line in json_logs() if line["logger"] == "app.access"]
    assert access["trace_id"] == format(span.context.trace_id, "032x")
    assert access["span_id"] == format(span.context.span_id, "016x")


async def test_the_unhandled_exception_log_line_keeps_the_trace_id(
    settings: Settings, spans: InMemorySpanExporter, json_logs: LogReader
) -> None:
    """Starlette logs this after the request span has ended; the fallback covers that."""
    transport = ASGITransport(app=_app_with_boom_route(settings), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/boom")

    [span] = _server_spans(spans)
    [failure] = [line for line in json_logs() if line["message"] == "Unhandled exception"]
    assert failure["trace_id"] == format(span.context.trace_id, "032x")


async def test_an_untraced_request_does_not_inherit_the_previous_requests_trace_id(
    client: AsyncClient, spans: InMemorySpanExporter, json_logs: LogReader
) -> None:
    await client.get("/no/such/route")
    await client.get("/health/live")

    [probe] = [line for line in json_logs() if line.get("route") == "/health/live"]
    assert probe["trace_id"] is None


async def test_service_and_database_spans_nest_under_the_request(
    db_client: AsyncClient, spans: InMemorySpanExporter
) -> None:
    """Needs TEST_DATABASE_URL. It also proves the trace context survives SQLAlchemy's bridge
    from async code into the synchronous engine where the statement hooks run."""
    created = await db_client.post(
        "/api/v1/users", json={"email": "trace@example.com", "name": "T"}
    )
    assert created.status_code == 201

    finished = spans.get_finished_spans()
    server = next(s for s in finished if s.name == "POST /api/v1/users")
    service = next(s for s in finished if s.name == "UserService.create_user")
    assert service.context.trace_id == server.context.trace_id
    assert service.parent is not None
    assert service.parent.span_id == server.context.span_id

    statements = [s for s in finished if s.kind == SpanKind.CLIENT]
    assert any(s.name == "INSERT" for s in statements)
    assert all(s.context.trace_id == server.context.trace_id for s in statements)
    assert any(
        s.parent is not None and s.parent.span_id == service.context.span_id for s in statements
    )
