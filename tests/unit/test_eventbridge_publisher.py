"""EventBridge has no "receive" API of its own, so these tests verify a publish actually
reached the bus by attaching a rule that routes matching events to a target SQS queue -
the standard way to assert on EventBridge behaviour under moto (and in AWS itself)."""

import json

import boto3
import pytest
from moto import mock_aws

from app.events.base import DomainEvent
from app.events.eventbridge import EventBridgeEventPublisher
from tests.unit.sqs_helpers import REGION, create_test_queue, receive_all

BUS_NAME = "test-bus"


def _create_bus_with_queue_target() -> str:
    """Call inside an active mock_aws() context. Returns the target queue's URL."""
    events_client = boto3.client("events", region_name=REGION)
    sqs_client = boto3.client("sqs", region_name=REGION)

    events_client.create_event_bus(Name=BUS_NAME)
    queue_url = create_test_queue("eventbridge-target")
    queue_arn = sqs_client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]

    events_client.put_rule(
        Name="route-order-events",
        EventBusName=BUS_NAME,
        EventPattern=json.dumps({"source": ["order-service"]}),
    )
    events_client.put_targets(
        Rule="route-order-events",
        EventBusName=BUS_NAME,
        Targets=[{"Id": "1", "Arn": queue_arn}],
    )
    return queue_url


async def test_publish_is_routed_to_a_matching_rule_target() -> None:
    with mock_aws():
        queue_url = _create_bus_with_queue_target()
        publisher = EventBridgeEventPublisher(BUS_NAME, REGION)
        event = DomainEvent(event_type="OrderCreated", data={"order_id": "abc"})

        await publisher.publish(event)

        [message] = receive_all(queue_url)
        envelope = json.loads(message["Body"])
        assert envelope["detail-type"] == "OrderCreated"
        assert envelope["source"] == "order-service"
        detail = envelope["detail"]
        assert detail["event_id"] == str(event.event_id)
        assert detail["data"] == {"order_id": "abc"}


async def test_an_event_with_a_non_matching_source_is_not_routed() -> None:
    with mock_aws():
        queue_url = _create_bus_with_queue_target()
        publisher = EventBridgeEventPublisher(BUS_NAME, REGION)
        # Same publisher, but a DomainEvent with a source the rule doesn't match.
        event = DomainEvent(event_type="OrderCreated", data={}, source="unrelated-service")

        await publisher.publish(event)

        assert receive_all(queue_url) == []


async def test_publish_raises_when_eventbridge_reports_a_failed_entry() -> None:
    with mock_aws():
        boto3.client("events", region_name=REGION).create_event_bus(Name=BUS_NAME)
        publisher = EventBridgeEventPublisher(BUS_NAME, REGION)

        def failing_put_events(**_: object) -> dict[str, object]:
            return {
                "FailedEntryCount": 1,
                "Entries": [{"ErrorCode": "InternalFailure", "ErrorMessage": "boom"}],
            }

        publisher._client.put_events = failing_put_events  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="InternalFailure"):
            await publisher.publish(DomainEvent(event_type="OrderCreated", data={}))
