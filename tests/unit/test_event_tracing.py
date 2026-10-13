"""Spans around event publication, and trace context carried in the SQS message attributes."""

import boto3
import pytest
from moto import mock_aws
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app.core.tracing import tracer
from app.events.base import DomainEvent
from app.events.eventbridge import EventBridgeEventPublisher
from app.events.sqs import SQSEventPublisher
from tests.unit.sqs_helpers import REGION, create_test_queue, receive_all

QUEUE = "order-events"
BUS = "order-bus"


def _only(spans: InMemorySpanExporter, name: str) -> ReadableSpan:
    [span] = [s for s in spans.get_finished_spans() if s.name == name]
    return span


def _event() -> DomainEvent:
    return DomainEvent(event_type="OrderCreated", data={"order_id": "o-1"})


async def test_an_sqs_publish_is_a_producer_span(spans: InMemorySpanExporter) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        await SQSEventPublisher(queue_url, REGION).publish(_event())

    span = _only(spans, f"send {QUEUE}")
    assert span.kind == SpanKind.PRODUCER
    assert span.attributes["messaging.system"] == "aws_sqs"
    assert span.attributes["messaging.destination.name"] == QUEUE
    assert span.attributes["app.event.type"] == "OrderCreated"
    assert span.status.status_code == StatusCode.UNSET


async def test_the_sqs_message_carries_the_send_spans_trace_context(
    spans: InMemorySpanExporter,
) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        with tracer.start_as_current_span("request") as root:
            await SQSEventPublisher(queue_url, REGION).publish(_event())
        [message] = receive_all(queue_url)

    send = _only(spans, f"send {QUEUE}")
    traceparent = message["MessageAttributes"]["traceparent"]["StringValue"]
    version, trace_id, span_id, _flags = traceparent.split("-")
    assert version == "00"
    assert trace_id == format(root.get_span_context().trace_id, "032x")
    assert span_id == format(send.context.span_id, "016x")  # the consumer's parent is the send
    assert send.parent is not None
    assert send.parent.span_id == root.get_span_context().span_id


async def test_a_publish_outside_any_trace_starts_one(spans: InMemorySpanExporter) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        await SQSEventPublisher(queue_url, REGION).publish(_event())
        [message] = receive_all(queue_url)

    send = _only(spans, f"send {QUEUE}")
    assert send.parent is None
    traceparent = message["MessageAttributes"]["traceparent"]["StringValue"]
    assert traceparent.split("-")[1] == format(send.context.trace_id, "032x")


async def test_an_sqs_failure_is_recorded_by_type_only(spans: InMemorySpanExporter) -> None:
    with mock_aws():
        queue_url = create_test_queue(QUEUE)
        publisher = SQSEventPublisher(queue_url, REGION)

        def failing_send(**_: object) -> None:
            raise RuntimeError("endpoint https://user:s3cr3t-pw@sqs.example is unreachable")

        publisher._client.send_message = failing_send  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await publisher.publish(_event())

    span = _only(spans, f"send {QUEUE}")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.events == ()
    assert "s3cr3t-pw" not in repr(dict(span.attributes)) + str(span.status.description)


async def test_an_eventbridge_publish_is_a_producer_span(spans: InMemorySpanExporter) -> None:
    with mock_aws():
        boto3.client("events", region_name=REGION).create_event_bus(Name=BUS)
        await EventBridgeEventPublisher(BUS, REGION).publish(_event())

    span = _only(spans, f"put_events {BUS}")
    assert span.kind == SpanKind.PRODUCER
    assert span.attributes["messaging.system"] == "aws_eventbridge"
    assert span.attributes["messaging.destination.name"] == BUS
    assert span.status.status_code == StatusCode.UNSET


async def test_a_rejected_eventbridge_entry_marks_the_span_as_an_error(
    spans: InMemorySpanExporter,
) -> None:
    with mock_aws():
        boto3.client("events", region_name=REGION).create_event_bus(Name=BUS)
        publisher = EventBridgeEventPublisher(BUS, REGION)

        def failing_put_events(**_: object) -> dict[str, object]:
            return {
                "FailedEntryCount": 1,
                "Entries": [{"ErrorCode": "InternalFailure", "ErrorMessage": "boom"}],
            }

        publisher._client.put_events = failing_put_events  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await publisher.publish(_event())

    span = _only(spans, f"put_events {BUS}")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert "boom" not in repr(dict(span.attributes)) + str(span.status.description)
