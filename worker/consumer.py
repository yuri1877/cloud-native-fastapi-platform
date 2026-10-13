"""SQS consumer loop: long-polls, dispatches to a handler, deletes on success.

A failed message is left on the queue (not deleted): SQS redelivers it after the
visibility timeout, and eventually routes it to the dead-letter queue once the redrive
policy's maxReceiveCount is exceeded (queue infrastructure: Phase 26). Idempotency is
enforced via `event_id` before a handler runs, so a redelivered-and-retried message that
already succeeded is skipped rather than reprocessed.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import boto3
from opentelemetry.trace import SpanKind

from app.core.tracing import extract_trace_context, mark_span_error, tracer
from worker.handlers import HANDLERS
from worker.idempotency import ProcessedEventTracker

if TYPE_CHECKING:
    from mypy_boto3_sqs.client import SQSClient

logger = logging.getLogger("worker")

POLL_WAIT_SECONDS = 20  # long polling: fewer empty-receive API calls, lower cost
MAX_MESSAGES_PER_POLL = 10
VISIBILITY_TIMEOUT_SECONDS = 30  # must exceed typical handler processing time


class Worker:
    def __init__(
        self,
        queue_url: str,
        region_name: str,
        tracker: ProcessedEventTracker,
        *,
        wait_time_seconds: int = POLL_WAIT_SECONDS,
        visibility_timeout_seconds: int = VISIBILITY_TIMEOUT_SECONDS,
    ) -> None:
        self._queue_url = queue_url
        self._queue_name = queue_url.rstrip("/").rsplit("/", 1)[-1]
        self._client: SQSClient = boto3.client("sqs", region_name=region_name)
        self._tracker = tracker
        self._wait_time_seconds = wait_time_seconds
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._shutdown = asyncio.Event()

    def request_shutdown(self) -> None:
        logger.info("Shutdown requested; finishing in-flight work before exiting")
        self._shutdown.set()

    async def run(self) -> None:
        logger.info("Worker started", extra={"queue_url": self._queue_url})
        while not self._shutdown.is_set():
            await self.poll_once()
        logger.info("Worker stopped")

    async def poll_once(self) -> int:
        """One receive-and-process cycle. Returns the number of messages handled; exposed
        separately from `run()` so tests can drive it without a real polling loop."""
        messages = await asyncio.to_thread(self._receive)
        for message in messages:
            if self._shutdown.is_set():
                break
            await self._process(message)
        return len(messages)

    def _receive(self) -> list[dict[str, Any]]:
        response = self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
            WaitTimeSeconds=self._wait_time_seconds,
            VisibilityTimeout=self._visibility_timeout_seconds,
            MessageAttributeNames=["All"],
        )
        return response.get("Messages", [])

    async def _process(self, message: dict[str, Any]) -> None:
        receipt_handle = message["ReceiptHandle"]
        try:
            payload = json.loads(message["Body"])
            event_id = payload["event_id"]
            event_type = payload["event_type"]
        except Exception:
            logger.exception("Failed to process message; leaving it for redelivery")
            return

        # The producer's trace context rides in the message attributes; a message from a
        # producer that sent none starts a new trace. The span name uses the event type only
        # if it is one we handle, so a foreign producer cannot create unbounded span names.
        span_event_type = event_type if event_type in HANDLERS else "unknown"
        with tracer.start_as_current_span(
            f"process {span_event_type}",
            context=extract_trace_context(_trace_carrier(message)),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "aws_sqs",
                "messaging.destination.name": self._queue_name,
                "messaging.operation.type": "process",
                "messaging.message.id": str(message.get("MessageId", "")),
                "app.event.id": str(event_id),
                "app.event.type": str(event_type),
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                if await self._tracker.already_processed(event_id):
                    logger.info("Skipping already-processed event", extra={"event_id": event_id})
                else:
                    handler = HANDLERS.get(event_type)
                    if handler is None:
                        logger.warning(
                            "No handler for event type", extra={"event_type": event_type}
                        )
                    else:
                        await handler(payload)
                    await self._tracker.mark_processed(event_id)

                await asyncio.to_thread(self._delete, receipt_handle)
            except Exception as exc:
                mark_span_error(span, exc)
                logger.exception("Failed to process message; leaving it for redelivery")

    def _delete(self, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)


def _trace_carrier(message: dict[str, Any]) -> dict[str, str]:
    """The string-valued message attributes, which is where the producer put its trace context.

    The queue is internal, so its attributes are trusted the way the producer is.
    """
    attributes = message.get("MessageAttributes") or {}
    return {
        name: value["StringValue"]
        for name, value in attributes.items()
        if isinstance(value, dict) and "StringValue" in value
    }
