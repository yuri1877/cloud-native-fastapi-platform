"""OpenTelemetry tracing.

Spans are created by hand at the few places that matter (the HTTP request, a service
operation, a database statement, an event publication, a worker message) rather than through
auto-instrumentation libraries; ADR-006 explains why.

The tracer provider is process-wide, as OpenTelemetry intends: `configure_tracing` builds it
once and later calls return the same one. Code gets a tracer with `trace.get_tracer`, which
returns a proxy that resolves to the real provider once it exists.

What a span may carry is deliberate. Exception *messages* are never copied into a span, and
neither is SQL text: both can contain personal data or credentials (SQLAlchemy errors print
the bound parameters). A span records the exception's type instead; the redacted message and
traceback are in the logs, which carry the same `trace_id`.
"""

import functools
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, Sampler, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.interfaces import ExceptionContext

from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.metrics import database_operation
from app.core.request_context import set_span_id, set_trace_id

tracer = trace.get_tracer("app")

# Only W3C trace context is propagated. Baggage is deliberately left out: it carries
# arbitrary key/values between services and would be accepted from untrusted callers.
_propagator = TraceContextTextMapPropagator()

# Key under which in-flight database spans are stacked on `Connection.info`.
TRACE_SPANS_KEY = "tracing_statement_spans"

_provider: TracerProvider | None = None


def build_sampler(ratio: float) -> Sampler:
    """Sample `ratio` of new traces; follow the caller's decision when there is one.

    A span that is not sampled still has valid trace and span IDs, so logs stay correlatable
    whatever the ratio.
    """
    return ParentBased(root=TraceIdRatioBased(ratio))


def build_span_processor(base_url: str) -> SpanProcessor:
    """Batch spans to an OTLP/HTTP collector at `base_url` (e.g. http://localhost:4318)."""
    # Imported here so the exporter and its protobuf dependency load only when one is wanted.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    # An explicit endpoint is used verbatim (unlike the env var, which gets the path appended).
    return BatchSpanProcessor(OTLPSpanExporter(endpoint=base_url.rstrip("/") + "/v1/traces"))


def configure_tracing(settings: Settings, *, service_name: str | None = None) -> TracerProvider:
    """Create and register the process-wide tracer provider; later calls return the same one.

    The first call wins, including for `service_name` and the sampling ratio. The API and the
    worker are separate processes, so each names itself.
    """
    global _provider
    if _provider is not None:
        return _provider

    resource = Resource.create(
        {
            "service.name": service_name or settings.app_name,
            "service.version": settings.app_version,
            "deployment.environment.name": settings.app_env,
        }
    )
    provider = TracerProvider(
        resource=resource, sampler=build_sampler(settings.tracing_sample_ratio)
    )
    if settings.otel_exporter_otlp_endpoint:
        provider.add_span_processor(build_span_processor(settings.otel_exporter_otlp_endpoint))
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def mark_span_error(span: Span, exc: BaseException) -> None:
    """Record a failure on `span` without copying the exception's message into the trace.

    An `AppException` below 500 (not found, conflict, ...) is ordinary control flow, not a
    fault, so it leaves the span's status alone and only notes the application error code.
    """
    if isinstance(exc, AppException):
        span.set_attribute("app.error.code", exc.code)
        if exc.status_code < 500:
            return
    span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))


def traced[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Run an async function inside a span named after it (`OrderService.create_order`)."""
    name = fn.__qualname__

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                mark_span_error(span, exc)
                raise

    return wrapper


def remember_trace(span: Span) -> None:
    """Keep the span's IDs as the request-level fallback for log correlation."""
    span_context = span.get_span_context()
    if span_context.is_valid:
        set_trace_id(format(span_context.trace_id, "032x"))
        set_span_id(format(span_context.span_id, "016x"))


def inject_trace_context() -> dict[str, str]:
    """The current span's context as `traceparent`/`tracestate` entries; empty if none."""
    carrier: dict[str, str] = {}
    _propagator.inject(carrier)
    return carrier


def extract_trace_context(carrier: Mapping[str, str]) -> Context:
    """A context carrying the remote span described by `carrier`; empty if it has none."""
    return _propagator.extract(carrier)


def attach_database_tracing(engine: Engine) -> None:
    """Give every statement run through `engine` a client span, when inside a trace.

    Pass `async_engine.sync_engine` for an AsyncEngine. A statement outside any trace (the
    readiness probe, a migration) gets no span rather than a parentless one. As with the
    metrics hooks, a failed statement never reaches `after_cursor_execute`, so `handle_error`
    ends its span; the failure is recorded by type only, because SQLAlchemy's error text
    includes the statement parameters.
    """
    system = engine.dialect.name

    def finish(connection: Connection, error: BaseException | None) -> None:
        spans = connection.info.get(TRACE_SPANS_KEY)
        if not spans:
            return
        span: Span = spans.pop()
        if error is not None:
            span.set_attribute("error.type", type(error).__qualname__)
            span.set_status(Status(StatusCode.ERROR, type(error).__name__))
        span.end()

    def before_cursor_execute(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if not trace.get_current_span().get_span_context().is_valid:
            return
        operation = database_operation(statement)
        span = tracer.start_span(
            operation,
            kind=SpanKind.CLIENT,
            attributes={"db.system.name": system, "db.operation.name": operation},
        )
        conn.info.setdefault(TRACE_SPANS_KEY, []).append(span)

    def after_cursor_execute(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        finish(conn, None)

    def handle_error(exception_context: ExceptionContext) -> None:
        connection = exception_context.connection
        if connection is not None and exception_context.statement is not None:
            finish(connection, exception_context.original_exception)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)
