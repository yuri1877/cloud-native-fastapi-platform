"""Structured JSON logging foundation.

Request-scoped fields (request_id, trace_id, HTTP fields) are added in later phases.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.request_context import get_request_id, get_trace_id


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
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
        }
        for field in ("http_method", "http_route", "http_status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Route all logs (including uvicorn's) to stdout as JSON."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(settings.app_name, settings.app_env))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
