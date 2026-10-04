import json
from typing import Any

import pytest
from moto import mock_aws

import worker.handlers
from app.events.base import DomainEvent
from app.events.sqs import SQSEventPublisher
from tests.unit.sqs_helpers import REGION, create_test_queue, receive_all
from worker.consumer import Worker
from worker.idempotency import InMemoryProcessedEventTracker


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, payload: dict[str, Any]) -> None:
        self.calls.append(payload)


@pytest.fixture
def recording_handler(monkeypatch: pytest.MonkeyPatch) -> RecordingHandler:
    handler = RecordingHandler()
    monkeypatch.setitem(worker.handlers.HANDLERS, "TestEvent", handler)
    return handler


async def test_poll_once_dispatches_to_the_matching_handler_and_deletes_on_success(
    recording_handler: RecordingHandler,
) -> None:
    with mock_aws():
        queue_url = create_test_queue()
        await SQSEventPublisher(queue_url, REGION).publish(
            DomainEvent(event_type="TestEvent", data={"k": "v"})
        )
        consumer = Worker(queue_url, REGION, InMemoryProcessedEventTracker(), wait_time_seconds=0)

        handled = await consumer.poll_once()

        assert handled == 1
        assert len(recording_handler.calls) == 1
        assert recording_handler.calls[0]["data"] == {"k": "v"}
        assert receive_all(queue_url) == []  # deleted after successful processing


async def test_unknown_event_type_is_deleted_without_error() -> None:
    """No handler registered -> logged and dropped, not retried forever."""
    with mock_aws():
        queue_url = create_test_queue()
        await SQSEventPublisher(queue_url, REGION).publish(
            DomainEvent(event_type="NoHandlerForThis", data={})
        )
        consumer = Worker(queue_url, REGION, InMemoryProcessedEventTracker(), wait_time_seconds=0)

        await consumer.poll_once()

        assert receive_all(queue_url) == []


async def test_a_failing_handler_leaves_the_message_for_redelivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_handler(payload: dict[str, Any]) -> None:
        raise RuntimeError("downstream dependency is unavailable")

    monkeypatch.setitem(worker.handlers.HANDLERS, "TestEvent", failing_handler)

    with mock_aws():
        queue_url = create_test_queue()
        await SQSEventPublisher(queue_url, REGION).publish(
            DomainEvent(event_type="TestEvent", data={})
        )
        # visibility_timeout_seconds=0: the message becomes visible again immediately, so
        # the test can observe redelivery without waiting for a real timeout to expire.
        consumer = Worker(
            queue_url,
            REGION,
            InMemoryProcessedEventTracker(),
            wait_time_seconds=0,
            visibility_timeout_seconds=0,
        )

        await consumer.poll_once()

        messages = receive_all(queue_url)
        assert len(messages) == 1  # still there: never deleted
        assert json.loads(messages[0]["Body"])["event_type"] == "TestEvent"


async def test_already_processed_event_is_skipped_not_reprocessed(
    recording_handler: RecordingHandler,
) -> None:
    with mock_aws():
        queue_url = create_test_queue()
        tracker = InMemoryProcessedEventTracker()
        consumer = Worker(queue_url, REGION, tracker, wait_time_seconds=0)

        event = DomainEvent(event_type="TestEvent", data={"k": "v"})
        body = event.model_dump_json()

        # Calls the private _process() directly: real SQS redelivery (new receipt handle,
        # same body) only happens after the visibility timeout expires, which there is no
        # need to wait for in a unit test - constructing the two deliveries directly is
        # equivalent and immediate.
        # First delivery: processed normally.
        await consumer._process({"Body": body, "ReceiptHandle": "handle-1"})
        assert len(recording_handler.calls) == 1

        # Simulated redelivery of the *same* event (SQS assigns a new receipt handle on
        # redelivery; the body, and therefore event_id, is unchanged).
        await consumer._process({"Body": body, "ReceiptHandle": "handle-2"})
        assert len(recording_handler.calls) == 1  # not called again
