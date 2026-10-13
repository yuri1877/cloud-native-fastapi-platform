"""Per-request correlation context, readable from anywhere (including the log formatter,
which has no access to the `Request` object)."""

import re
import uuid
from contextvars import ContextVar

from opentelemetry import trace

REQUEST_ID_HEADER = "X-Request-ID"

# Conservative allowlist: alphanumerics, hyphen, underscore. Blocks header/log injection
# (CRLF, control characters) and unbounded-length headers. UUIDs and ULIDs both match.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
# Request-level fallbacks for the trace/span IDs: see `get_trace_id`.
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


def generate_request_id() -> str:
    return uuid.uuid4().hex


def is_safe_request_id(value: str) -> bool:
    """Whether an inbound X-Request-ID is safe to echo back and log verbatim.

    This is a format check only, never a security identity: an inbound ID is never
    trusted as proof of who the caller is.
    """
    return bool(_SAFE_ID_PATTERN.match(value))


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_trace_id() -> str | None:
    """The trace ID to put on a log line, as 32 hex characters.

    The live OpenTelemetry span wins. When none is active, the request-level fallback set by
    the middleware is used: an unhandled exception is logged by Starlette's error handler
    *after* the request span has ended, and that line is exactly the one that must carry the
    trace ID. Outside a request (and outside any span) this is None.
    """
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        return format(span_context.trace_id, "032x")
    return _trace_id.get()


def get_span_id() -> str | None:
    """As `get_trace_id`, for the span ID (16 hex characters)."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        return format(span_context.span_id, "016x")
    return _span_id.get()


def set_trace_id(value: str | None) -> None:
    """Set the request-level fallback trace ID (see `get_trace_id`)."""
    _trace_id.set(value)


def set_span_id(value: str | None) -> None:
    """Set the request-level fallback span ID (see `get_trace_id`)."""
    _span_id.set(value)
