"""SQS implementation of the EventPublisher protocol (app/events/base.py).

boto3 is synchronous, so calls run in a thread via `asyncio.to_thread` rather than blocking
the event loop. A standard (non-FIFO) queue is used - deduplication is the consumer's
responsibility (see worker/idempotency.py), keyed on `event_id`, which is simpler to operate
than a FIFO queue and matches the throughput needs of this platform.
"""

import asyncio
from typing import TYPE_CHECKING

import boto3

from app.events.base import DomainEvent

if TYPE_CHECKING:
    from mypy_boto3_sqs.client import SQSClient


class SQSEventPublisher:
    def __init__(self, queue_url: str, region_name: str) -> None:
        self._queue_url = queue_url
        # Constructing a client does not open a connection; no network call happens here.
        self._client: SQSClient = boto3.client("sqs", region_name=region_name)

    async def publish(self, event: DomainEvent) -> None:
        await asyncio.to_thread(self._send, event)

    def _send(self, event: DomainEvent) -> None:
        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=event.model_dump_json(),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": event.event_type},
                "event_version": {"DataType": "String", "StringValue": event.event_version},
            },
        )
