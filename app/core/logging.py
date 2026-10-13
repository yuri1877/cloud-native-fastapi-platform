"""Structured JSON logging.

Every record is one JSON object on stdout: the canonical fields (timestamp, level, service,
environment, logger, message, request_id, trace_id) plus whatever structured `extra={...}`
fields the caller supplied.

Secrets are redacted as a backstop (`redact_text` / `redact_value`). The primary control is
never to log them in the first place; redaction catches mistakes, it does not excuse them.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.request_context import get_request_id, get_span_id, get_trace_id

REDACTED = "[REDACTED]"

# Attributes every LogRecord has. Anything else on a record arrived via `extra=`.
_STANDARD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}

# A key containing any of these (case-insensitive) has its value replaced outright.
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "private_key",
    "database_url",
)

_BEARER = re.compile(r"\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_URL_PASSWORD = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+(?=@)", re.IGNORECASE
)

# Third-party loggers that can emit request headers or bodies at DEBUG. Held at WARNING or
# above whatever LOG_LEVEL is, so debugging the app cannot leak AWS credentials/tokens.
_NOISY_LOGGERS = ("botocore", "boto3", "urllib3")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact_text(text: str) -> str:
    """Scrub bearer tokens, JWTs and passwords embedded in URLs from free text."""
    text = _BEARER.sub(r"\1 " + REDACTED, text)
    text = _JWT.sub(REDACTED, text)
    return _URL_PASSWORD.sub(r"\g<prefix>" + REDACTED, text)


def redact_value(value: Any, key: str | None = None) -> Any:
    """Redact by key name first, then by content, recursing into dicts and lists."""
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "environment": self._environment,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
            "span_id": get_span_id(),
        }
        # Structured fields from `extra=`. Canonical fields always win a name clash, so a
        # caller cannot spoof `service`, `request_id` etc.
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRIBUTES or key.startswith("_") or key in payload:
                continue
            payload[key] = redact_value(value, key)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Route all logs (including uvicorn's) to stdout as JSON."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(settings.app_name, settings.app_env))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # RequestIDMiddleware writes one richer access line per request, and unlike uvicorn's
    # it never includes the query string (which can carry tokens). Silence the duplicate.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False

    noisy_level = max(getattr(logging, settings.log_level), logging.WARNING)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(noisy_level)
