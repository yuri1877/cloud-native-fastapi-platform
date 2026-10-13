"""SQS implementation of the EventPublisher protocol (app/events/base.py).

boto3 is synchronous, so calls run in a thread via `asyncio.to_thread` rather than blocking
the event loop. A standard (non-FIFO) queue is used - deduplication is the consumer's
responsibility (see worker/idempotency.py), keyed on `event_id`, which is simpler to operate
than a FIFO queue and matches the throughput needs of this platform.

Each publish is a `PRODUCER` span, and its W3C trace context travels in the message
attributes (`traceparent`/`tracestate`), so the worker's processing span joins the same
trace. Trace context is transport metadata, so it is not part of the event envelope.
"""

import asyncio
from typing import TYPE_CHECKING, Any

import boto3
from opentelemetry.trace import SpanKind

from app.core.tracing import inject_trace_context, mark_span_error, tracer
from app.events.base import DomainEvent

if TYPE_CHECKING:
    from mypy_boto3_sqs.client import SQSClient


class SQSEventPublisher:
    def __init__(self, queue_url: str, region_name: str) -> None:
        self._queue_url = queue_url
        self._queue_name = queue_url.rstrip("/").rsplit("/", 1)[-1]
        # Constructing a client does not open a connection; no network call happens here.
        self._client: SQSClient = boto3.client("sqs", region_name=region_name)

    async def publish(self, event: DomainEvent) -> None:
        with tracer.start_as_current_span(
            f"send {self._queue_name}",
            kind=SpanKind.PRODUCER,
            attributes={
                "messaging.system": "aws_sqs",
                "messaging.destination.name": self._queue_name,
                "messaging.operation.type": "send",
                "app.event.type": event.event_type,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            # Injected inside the span, so the consumer's parent is this send span.
            trace_context = inject_trace_context()
            try:
                await asyncio.to_thread(self._send, event, trace_context)
            except Exception as exc:
                mark_span_error(span, exc)
                raise

    def _send(self, event: DomainEvent, trace_context: dict[str, str]) -> None:
        attributes: dict[str, Any] = {
            "event_type": {"DataType": "String", "StringValue": event.event_type},
            "event_version": {"DataType": "String", "StringValue": event.event_version},
        }
        for name, value in trace_context.items():
            attributes[name] = {"DataType": "String", "StringValue": value}
        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=event.model_dump_json(),
            MessageAttributes=attributes,
        )
