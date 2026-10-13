"""The worker continues the producer's trace, so one trace spans API request -> SQS -> worker."""

from collections.abc import Callable
from typing import Any

import boto3
import pytest
from moto import mock_aws
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

import worker.handlers
from app.core.tracing import tracer
from app.events.base import DomainEvent
from app.events.sqs import SQSEventPublisher
from tests.unit.sqs_helpers import REGION, create_test_queue
from worker.consumer import Worker
from worker.idempotency import InMemoryProcessedEventTracker

QUEUE = "order-events"

LogReader = Callable[[], list[dict[str, Any]]]


def _only(spans: InMemorySpanExporter, name: str) -> ReadableSpan:
    [span] = [s for s in spans.get_finished_spans() if s.name == name]
    return span


def _worker(queue_url: str, **kwargs: Any) -> Worker:
    return Worker(queue_url, REGION, InMemoryProcessedEventTracker(), wait_time_seconds=0, **kwargs)


async def test_the_worker_continues_the_producers_trace_and_its_logs_carry_the_ids(
    spans: InMemorySpanExporter, json_logs: LogReader
) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        with tracer.start_as_current_span("request") as root:
            await SQSEventPublisher(queue_url, REGION).publish(
                DomainEvent(event_type="OrderCreated", data={"order_id": "o-1", "user_id": "u-1"})
            )
        await _worker(queue_url).poll_once()

    send = _only(spans, f"send {QUEUE}")
    process = _only(spans, "process OrderCreated")
    root_context = root.get_span_context()
    assert process.kind == SpanKind.CONSUMER
    assert process.context.trace_id == root_context.trace_id
    assert process.parent is not None
    assert process.parent.span_id == send.context.span_id
    assert process.attributes["messaging.operation.type"] == "process"
    assert process.attributes["app.event.type"] == "OrderCreated"

    # The real handler logs inside the process span, so its line joins the same trace.
    [line] = [entry for entry in json_logs() if entry["logger"] == "worker.handlers"]
    assert line["trace_id"] == format(root_context.trace_id, "032x")
    assert line["span_id"] == format(process.context.span_id, "016x")


async def test_a_message_without_trace_context_starts_a_new_trace(
    spans: InMemorySpanExporter,
) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        boto3.client("sqs", region_name=REGION).send_message(
            QueueUrl=queue_url,
            MessageBody=DomainEvent(event_type="OrderCreated", data={}).model_dump_json(),
        )
        await _worker(queue_url).poll_once()

    process = _only(spans, "process OrderCreated")
    assert process.parent is None


async def test_unrecognised_event_types_share_one_span_name(
    spans: InMemorySpanExporter,
) -> None:
    """A foreign producer must not be able to create unbounded span names."""
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        await SQSEventPublisher(queue_url, REGION).publish(
            DomainEvent(event_type="SomethingForeign", data={})
        )
        await _worker(queue_url).poll_once()

    process = _only(spans, "process unknown")
    assert process.attributes["app.event.type"] == "SomethingForeign"


async def test_a_failing_handler_marks_the_process_span_as_an_error_without_its_message(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_handler(payload: dict[str, Any]) -> None:
        raise RuntimeError("customer 42 secret detail")

    monkeypatch.setitem(worker.handlers.HANDLERS, "TestEvent", failing_handler)

    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        await SQSEventPublisher(queue_url, REGION).publish(
            DomainEvent(event_type="TestEvent", data={})
        )
        await _worker(queue_url, visibility_timeout_seconds=0).poll_once()

    process = _only(spans, "process TestEvent")
    assert process.status.status_code == StatusCode.ERROR
    assert process.attributes["error.type"] == "RuntimeError"
    assert process.events == ()
    assert "secret detail" not in repr(dict(process.attributes)) + str(process.status.description)
