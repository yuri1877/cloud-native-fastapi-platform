"""trace_id and span_id on log lines: the live span wins, the request-level fallback covers
the moment after the span has ended, and outside any trace both are null."""

import contextvars
import json
import logging
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanContext

from app.core.logging import JsonFormatter
from app.core.request_context import set_span_id, set_trace_id

FALLBACK_TRACE_ID = "a" * 32
FALLBACK_SPAN_ID = "b" * 16


def _format() -> dict[str, Any]:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)
    return json.loads(JsonFormatter("svc", "test").format(record))


def _inside_a_span(set_fallback: bool) -> tuple[dict[str, Any], SpanContext]:
    if set_fallback:
        set_trace_id(FALLBACK_TRACE_ID)
        set_span_id(FALLBACK_SPAN_ID)
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("x") as span:
        return _format(), span.get_span_context()


def test_both_ids_are_null_outside_any_trace() -> None:
    payload = contextvars.Context().run(_format)
    assert payload["trace_id"] is None
    assert payload["span_id"] is None


def test_the_live_span_supplies_the_ids() -> None:
    payload, span_context = contextvars.Context().run(_inside_a_span, False)

    assert payload["trace_id"] == format(span_context.trace_id, "032x")
    assert payload["span_id"] == format(span_context.span_id, "016x")
    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16


def test_the_request_fallback_is_used_when_no_span_is_live() -> None:
    def run() -> dict[str, Any]:
        set_trace_id(FALLBACK_TRACE_ID)
        set_span_id(FALLBACK_SPAN_ID)
        return _format()

    payload = contextvars.Context().run(run)
    assert payload["trace_id"] == FALLBACK_TRACE_ID
    assert payload["span_id"] == FALLBACK_SPAN_ID


def test_a_live_span_beats_the_fallback() -> None:
    payload, span_context = contextvars.Context().run(_inside_a_span, True)

    assert payload["trace_id"] == format(span_context.trace_id, "032x")
    assert payload["span_id"] == format(span_context.span_id, "016x")
