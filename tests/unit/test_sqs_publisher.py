import json

from moto import mock_aws

from app.events.base import DomainEvent
from app.events.sqs import SQSEventPublisher
from tests.unit.sqs_helpers import REGION, create_test_queue, receive_all


async def test_publish_sends_the_event_as_the_message_body() -> None:
    with mock_aws():
        queue_url = create_test_queue()
        publisher = SQSEventPublisher(queue_url, REGION)
        event = DomainEvent(event_type="OrderCreated", data={"order_id": "abc", "user_id": "xyz"})

        await publisher.publish(event)

        [message] = receive_all(queue_url)
        body = json.loads(message["Body"])
        assert body["event_id"] == str(event.event_id)
        assert body["event_type"] == "OrderCreated"
        assert body["data"] == {"order_id": "abc", "user_id": "xyz"}


async def test_publish_sets_message_attributes() -> None:
    with mock_aws():
        queue_url = create_test_queue()
        publisher = SQSEventPublisher(queue_url, REGION)
        event = DomainEvent(event_type="OrderCreated", data={})

        await publisher.publish(event)

        [message] = receive_all(queue_url)
        attributes = message["MessageAttributes"]
        assert attributes["event_type"]["StringValue"] == "OrderCreated"
        assert attributes["event_version"]["StringValue"] == "1"


async def test_publish_each_call_sends_one_message() -> None:
    with mock_aws():
        queue_url = create_test_queue()
        publisher = SQSEventPublisher(queue_url, REGION)

        await publisher.publish(DomainEvent(event_type="OrderCreated", data={}))
        await publisher.publish(DomainEvent(event_type="OrderCreated", data={}))

        assert len(receive_all(queue_url)) == 2
