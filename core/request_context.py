"""Per-request correlation context, readable from anywhere (including the log formatter,
which has no access to the `Request` object)."""

import re
import uuid
from contextvars import ContextVar

# Conservative allowlist: alphanumerics, hyphen, underscore. Blocks header/log injection
# (CRLF, control characters) and unbounded-length headers. UUIDs and ULIDs both match.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


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
    """Populated once distributed tracing is added (Phase 16); None until then."""
    return _trace_id.get()


def set_trace_id(value: str | None) -> None:
    _trace_id.set(value)
