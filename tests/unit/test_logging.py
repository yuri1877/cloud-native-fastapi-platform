import contextvars
import json
import logging
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.core.logging import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    redact_text,
)
from app.core.request_context import set_request_id, set_trace_id
from worker.handlers import handle_order_created

FAKE_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"
LEAKY_DB_URL = "postgresql+asyncpg://app:s3cr3t-pw@db:5432/app"


def _format(
    msg: str = "hello",
    *,
    args: tuple[Any, ...] = (),
    levelno: int = logging.INFO,
    exc_info: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    record = logging.LogRecord("app.test", levelno, __file__, 1, msg, args, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)  # this is what logging does with `extra={...}`
    return json.loads(JsonFormatter("svc", "test").format(record))


def _in_clean_context(fn: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Run with fresh context variables so request/trace IDs set by other tests (or by the
    code under test) cannot leak in or out."""
    return contextvars.Context().run(fn, **kwargs)


# --- canonical fields -------------------------------------------------------------------


def test_emits_all_canonical_fields() -> None:
    payload = _in_clean_context(_format, msg="hello %s", args=("world",))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["service"] == "svc"
    assert payload["environment"] == "test"
    assert payload["logger"] == "app.test"
    assert payload["request_id"] is None
    assert payload["trace_id"] is None
    datetime.fromisoformat(payload["timestamp"])  # must be a valid ISO-8601 timestamp


def test_request_and_trace_ids_come_from_context() -> None:
    def run() -> dict[str, Any]:
        set_request_id("req-12345678")
        set_trace_id("trace-abc")
        return _format()

    payload = contextvars.Context().run(run)
    assert payload["request_id"] == "req-12345678"
    assert payload["trace_id"] == "trace-abc"


# --- structured extras ------------------------------------------------------------------


def test_extra_fields_are_included() -> None:
    payload = _format(
        method="GET", route="/health/live", status_code=200, duration_ms=1.5, order_id="o-1"
    )
    assert payload["method"] == "GET"
    assert payload["route"] == "/health/live"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.5
    assert payload["order_id"] == "o-1"


def test_extra_fields_cannot_override_canonical_fields() -> None:
    payload = _in_clean_context(_format, service="evil", request_id="spoofed", level="FATAL")
    assert payload["service"] == "svc"
    assert payload["request_id"] is None
    assert payload["level"] == "INFO"


def test_non_json_values_are_stringified_not_fatal() -> None:
    value = uuid.uuid4()
    assert _format(order_id=value)["order_id"] == str(value)


def test_ordinary_identifiers_are_not_mistaken_for_secrets() -> None:
    payload = _format(order_id="o-1", user_id="u-1", event_id="e-1", queue_url="https://q")
    assert payload["order_id"] == "o-1"
    assert payload["user_id"] == "u-1"
    assert payload["event_id"] == "e-1"
    assert payload["queue_url"] == "https://q"


async def test_worker_handler_fields_reach_the_log_output(
    json_logs: Callable[[], list[dict[str, Any]]],
) -> None:
    """Regression: the formatter used to drop every extra field outside a fixed allowlist,
    so the worker's order_id/user_id never appeared in the output."""
    await handle_order_created({"data": {"order_id": "o-1", "user_id": "u-1"}})
    [line] = [entry for entry in json_logs() if entry["logger"] == "worker.handlers"]
    assert line["order_id"] == "o-1"
    assert line["user_id"] == "u-1"


# --- redaction --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["password", "Authorization", "access_token", "client_secret", "database_url", "Cookie"],
)
def test_sensitive_extra_keys_are_redacted(key: str) -> None:
    payload = _format(**{key: "super-secret-value"})
    assert payload[key] == REDACTED
    assert "super-secret-value" not in json.dumps(payload)


def test_nested_structures_are_redacted() -> None:
    payload = _format(
        context={
            "headers": {"authorization": "Bearer abc123"},
            "items": ["Bearer xyz789"],
            "order_id": "o-1",
        }
    )
    assert payload["context"]["headers"]["authorization"] == REDACTED
    assert payload["context"]["items"] == [f"Bearer {REDACTED}"]
    assert payload["context"]["order_id"] == "o-1"


@pytest.mark.parametrize(
    ("message", "leaked"),
    [
        ("auth failed for Bearer abc.def-123_xyz==", "abc.def-123_xyz"),
        (f"bad token {FAKE_JWT}", FAKE_JWT),
        (f"cannot connect to {LEAKY_DB_URL}", "s3cr3t-pw"),
    ],
)
def test_secrets_in_messages_are_redacted(message: str, leaked: str) -> None:
    payload = _format(message)
    assert leaked not in payload["message"]
    assert REDACTED in payload["message"]


def test_secrets_in_message_arguments_are_redacted() -> None:
    payload = _format("login with %s", args=(f"Bearer {FAKE_JWT}",))
    assert FAKE_JWT not in payload["message"]


def test_exception_text_is_redacted() -> None:
    try:
        raise RuntimeError(f"cannot connect to {LEAKY_DB_URL}")
    except RuntimeError:
        payload = _format("failed", exc_info=sys.exc_info())
    assert "RuntimeError" in payload["exception"]
    assert "s3cr3t-pw" not in payload["exception"]


def test_ordinary_text_is_left_alone() -> None:
    assert redact_text("order o-1 created for user u-1") == "order o-1 created for user u-1"


# --- configure_logging ------------------------------------------------------------------


@contextmanager
def _preserved_logging_state() -> Iterator[None]:
    """configure_logging mutates process-wide logger state; put it back afterwards."""
    saved = []
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "botocore", "boto3", "urllib3"):
        logger = logging.getLogger(name)
        saved.append((logger, logger.handlers[:], logger.level, logger.propagate))
    try:
        yield
    finally:
        for logger, handlers, level, propagate in saved:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate


def test_configure_logging_writes_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, app_env="test", log_level="INFO")
    with _preserved_logging_state():
        configure_logging(settings)
        logging.getLogger("app.test").info("hello", extra={"order_id": "o-1"})
        output = capsys.readouterr().out

    payload = json.loads(output.strip().splitlines()[-1])
    assert payload["message"] == "hello"
    assert payload["order_id"] == "o-1"
    assert payload["service"] == settings.app_name
    assert payload["environment"] == "test"


def test_configure_logging_silences_the_duplicate_uvicorn_access_log() -> None:
    settings = Settings(_env_file=None, app_env="test")
    with _preserved_logging_state():
        configure_logging(settings)
        assert logging.getLogger("uvicorn.access").propagate is False
        assert logging.getLogger("uvicorn.error").propagate is True


@pytest.mark.parametrize(
    ("log_level", "expected"),
    [("DEBUG", logging.WARNING), ("INFO", logging.WARNING), ("ERROR", logging.ERROR)],
)
def test_noisy_third_party_loggers_never_log_below_warning(log_level: str, expected: int) -> None:
    settings = Settings(_env_file=None, app_env="test", log_level=log_level)
    with _preserved_logging_state():
        configure_logging(settings)
        for name in ("botocore", "boto3", "urllib3"):
            assert logging.getLogger(name).level == expected
