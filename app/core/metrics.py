"""Prometheus metrics.

One `Metrics` instance, with its own `CollectorRegistry`, is created per application (see
`create_app`). The process-wide default registry is deliberately not used: tests build many
apps in one process, and registering the same metric name twice in a shared registry raises.

Every label value must come from a small, bounded set, because each distinct combination
becomes its own time series. That is why `route` is a path *template* (never a raw path) and
why unrecognised HTTP methods are collapsed into one label value.
"""

import re
import time
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.interfaces import ExceptionContext

OTHER = "OTHER"

# A client can send any token as the HTTP method. Anything outside this set is recorded as
# OTHER so a caller cannot mint new time series by varying the method.
HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
DATABASE_OPERATIONS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})

# Bucket boundaries fix the resolution of every latency percentile computed from the
# histograms; revisit them against the Phase 31 load-test results.
HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
DATABASE_DURATION_BUCKETS = (
    0.001,
    0.0025,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
)

# Key under which statement start times are stacked on `Connection.info`.
START_TIMES_KEY = "metrics_statement_start_times"

_FIRST_WORD = re.compile(r"\s*([A-Za-z]+)")


def database_operation(statement: str) -> str:
    """The statement's leading keyword if it is a plain DML verb, otherwise OTHER.

    Only the verb is used, never table names or SQL text, to keep the label bounded. A
    statement that opens with a comment or a `WITH` clause is therefore recorded as OTHER.
    """
    match = _FIRST_WORD.match(statement)
    word = match.group(1).upper() if match else ""
    return word if word in DATABASE_OPERATIONS else OTHER


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self._http_requests = Counter(
            "http_requests_total",
            "HTTP requests handled, by method, route template and status code.",
            ["method", "route", "status_code"],
            registry=self.registry,
        )
        self._http_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds, by method and route template.",
            ["method", "route"],
            buckets=HTTP_DURATION_BUCKETS,
            registry=self.registry,
        )
        self._http_errors = Counter(
            "http_errors_total",
            "HTTP responses with a 5xx status, by method and route template.",
            ["method", "route"],
            registry=self.registry,
        )
        self._database_duration = Histogram(
            "database_operation_duration_seconds",
            "Database statement latency in seconds, by operation.",
            ["operation"],
            buckets=DATABASE_DURATION_BUCKETS,
            registry=self.registry,
        )

    def observe_request(
        self, *, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        method_label = method if method in HTTP_METHODS else OTHER
        self._http_requests.labels(method_label, route, str(status_code)).inc()
        self._http_duration.labels(method_label, route).observe(duration_seconds)
        if status_code >= 500:
            self._http_errors.labels(method_label, route).inc()

    def observe_database(self, *, operation: str, duration_seconds: float) -> None:
        self._database_duration.labels(operation).observe(duration_seconds)

    def render(self) -> bytes:
        """The Prometheus text exposition format, as served by GET /metrics."""
        return generate_latest(self.registry)


def attach_database_metrics(engine: Engine, metrics: Metrics) -> None:
    """Time every statement run through `engine`.

    Pass `async_engine.sync_engine` for an AsyncEngine: SQLAlchemy fires these events from the
    synchronous engine underneath it. Start times are stacked on `Connection.info`, which
    lives as long as the pooled DBAPI connection. A failed statement never reaches
    `after_cursor_execute`, so `handle_error` pops and records it instead; without that the
    stack would grow by one entry per failure.
    """

    def finish(connection: Connection, statement: str) -> None:
        starts = connection.info.get(START_TIMES_KEY)
        if starts:
            metrics.observe_database(
                operation=database_operation(statement),
                duration_seconds=time.perf_counter() - starts.pop(),
            )

    def before_cursor_execute(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info.setdefault(START_TIMES_KEY, []).append(time.perf_counter())

    def after_cursor_execute(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        finish(conn, statement)

    def handle_error(exception_context: ExceptionContext) -> None:
        connection = exception_context.connection
        statement = exception_context.statement
        if connection is not None and statement is not None:
            finish(connection, statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)
