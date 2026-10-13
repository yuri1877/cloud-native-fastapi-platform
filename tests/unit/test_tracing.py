import contextvars

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppException, NotFoundException
from app.core.tracing import (
    build_sampler,
    build_span_processor,
    configure_tracing,
    extract_trace_context,
    inject_trace_context,
    traced,
)

SAMPLED_PARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
UNSAMPLED_PARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"


# --- settings -------------------------------------------------------------------------


def test_tracing_settings_default_to_safe_values() -> None:
    settings = Settings(_env_file=None)
    assert settings.otel_exporter_otlp_endpoint is None
    assert settings.tracing_sample_ratio == 1.0
    assert settings.tracing_trust_inbound_context is False


@pytest.mark.parametrize("ratio", [-0.1, 1.5])
def test_the_sample_ratio_is_bounded(ratio: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tracing_sample_ratio=ratio)


# --- provider and sampling --------------------------------------------------------------


def test_configure_tracing_returns_the_same_provider_every_time() -> None:
    first = configure_tracing(Settings(_env_file=None, app_env="test"))
    second = configure_tracing(Settings(_env_file=None, app_env="test", tracing_sample_ratio=0.1))

    assert first is second
    assert trace.get_tracer_provider() is first


def test_an_unsampled_span_still_has_valid_ids() -> None:
    """Logs stay correlatable whatever the sampling ratio."""
    tracer = TracerProvider(sampler=build_sampler(0.0)).get_tracer("test")
    with tracer.start_as_current_span("x") as span:
        assert not span.is_recording()
        assert span.get_span_context().is_valid


def test_a_sampled_remote_parent_is_followed_whatever_the_ratio() -> None:
    """This is why inbound trace context is not trusted by default."""
    tracer = TracerProvider(sampler=build_sampler(0.0)).get_tracer("test")
    parent = extract_trace_context({"traceparent": SAMPLED_PARENT})
    with tracer.start_as_current_span("x", context=parent) as span:
        assert span.is_recording()


def test_an_unsampled_remote_parent_is_followed_too() -> None:
    tracer = TracerProvider(sampler=build_sampler(1.0)).get_tracer("test")
    parent = extract_trace_context({"traceparent": UNSAMPLED_PARENT})
    with tracer.start_as_current_span("x", context=parent) as span:
        assert not span.is_recording()


def test_the_otlp_processor_is_built_without_touching_the_network() -> None:
    processor = build_span_processor("http://localhost:4318/")
    try:
        assert isinstance(processor, BatchSpanProcessor)
    finally:
        processor.shutdown()


# --- context propagation ----------------------------------------------------------------


def test_nothing_is_injected_outside_a_span() -> None:
    assert contextvars.Context().run(inject_trace_context) == {}


def test_an_injected_context_extracts_back_to_the_same_span() -> None:
    tracer = TracerProvider().get_tracer("test")

    def run() -> tuple[dict[str, str], trace.SpanContext]:
        with tracer.start_as_current_span("x") as span:
            return inject_trace_context(), span.get_span_context()

    carrier, original = contextvars.Context().run(run)
    assert "traceparent" in carrier

    remote = trace.get_current_span(extract_trace_context(carrier)).get_span_context()
    assert remote.trace_id == original.trace_id
    assert remote.span_id == original.span_id
    assert remote.is_remote


@pytest.mark.parametrize("header", ["garbage", "", "00-short-short-01"])
def test_a_malformed_traceparent_is_ignored(header: str) -> None:
    context = extract_trace_context({"traceparent": header})
    assert not trace.get_current_span(context).get_span_context().is_valid


def test_a_carrier_without_a_traceparent_yields_no_parent() -> None:
    context = extract_trace_context({"unrelated": "header"})
    assert not trace.get_current_span(context).get_span_context().is_valid


# --- the traced decorator ---------------------------------------------------------------


class _Thing:
    @traced
    async def double(self, value: int) -> int:
        return value * 2

    @traced
    async def missing(self) -> None:
        raise NotFoundException("no such thing", code="THING_NOT_FOUND")

    @traced
    async def unavailable(self) -> None:
        raise AppException("dependency down", code="DEPENDENCY_DOWN", status_code=503)

    @traced
    async def explode(self) -> None:
        raise RuntimeError("connecting with password=hunter2 failed")

    @traced
    async def outer(self) -> int:
        return await self.double(1)


def _only(spans: InMemorySpanExporter, name: str) -> ReadableSpan:
    [span] = [s for s in spans.get_finished_spans() if s.name == name]
    return span


async def test_a_traced_call_returns_its_value_inside_a_span_named_after_it(
    spans: InMemorySpanExporter,
) -> None:
    assert await _Thing().double(21) == 42

    span = _only(spans, "_Thing.double")
    assert span.status.status_code == StatusCode.UNSET


def test_the_decorator_preserves_the_function_name() -> None:
    assert _Thing.double.__name__ == "double"


async def test_a_nested_traced_call_is_a_child_span(spans: InMemorySpanExporter) -> None:
    await _Thing().outer()

    outer = _only(spans, "_Thing.outer")
    inner = _only(spans, "_Thing.double")
    assert inner.parent is not None
    assert inner.parent.span_id == outer.context.span_id
    assert inner.context.trace_id == outer.context.trace_id


async def test_a_client_error_is_not_a_span_error(spans: InMemorySpanExporter) -> None:
    """Not-found and conflict are ordinary outcomes, so they must not light up error traces."""
    with pytest.raises(NotFoundException):
        await _Thing().missing()

    span = _only(spans, "_Thing.missing")
    assert span.status.status_code == StatusCode.UNSET
    assert span.attributes["app.error.code"] == "THING_NOT_FOUND"
    assert "error.type" not in span.attributes


async def test_a_server_side_application_error_is_a_span_error(
    spans: InMemorySpanExporter,
) -> None:
    with pytest.raises(AppException):
        await _Thing().unavailable()

    span = _only(spans, "_Thing.unavailable")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["app.error.code"] == "DEPENDENCY_DOWN"


async def test_an_unexpected_error_records_its_type_and_never_its_message(
    spans: InMemorySpanExporter,
) -> None:
    with pytest.raises(RuntimeError):
        await _Thing().explode()

    span = _only(spans, "_Thing.explode")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.events == ()  # no exception event, which would carry message and traceback
    assert "hunter2" not in repr(dict(span.attributes)) + str(span.status.description)
