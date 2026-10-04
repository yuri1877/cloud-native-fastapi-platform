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

            if await self._tracker.already_processed(event_id):
                logger.info("Skipping already-processed event", extra={"event_id": event_id})
            else:
                handler = HANDLERS.get(event_type)
                if handler is None:
                    logger.warning("No handler for event type", extra={"event_type": event_type})
                else:
                    await handler(payload)
                await self._tracker.mark_processed(event_id)

            await asyncio.to_thread(self._delete, receipt_handle)
        except Exception:
            logger.exception("Failed to process message; leaving it for redelivery")

    def _delete(self, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)
