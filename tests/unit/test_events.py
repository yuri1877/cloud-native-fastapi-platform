import uuid

import pytest
from pydantic import ValidationError

from app.events.base import DomainEvent
from app.events.order_events import order_created_event
from app.events.publishers import InMemoryEventPublisher, MultiEventPublisher


def test_domain_event_has_required_fields() -> None:
    event = DomainEvent(event_type="Something", data={"a": 1})
    assert event.event_version == "1"
    assert event.source == "order-service"
    assert isinstance(event.event_id, uuid.UUID)
    assert event.occurred_at is not None


def test_domain_event_is_frozen() -> None:
    event = DomainEvent(event_type="Something", data={})
    with pytest.raises(ValidationError):
        event.event_type = "Else"  # type: ignore[misc]


def test_each_event_gets_a_unique_id() -> None:
    a = DomainEvent(event_type="Something", data={})
    b = DomainEvent(event_type="Something", data={})
    assert a.event_id != b.event_id


def test_order_created_event_shape() -> None:
    order_id, user_id = uuid.uuid4(), uuid.uuid4()
    event = order_created_event(order_id=order_id, user_id=user_id)
    assert event.event_type == "OrderCreated"
    assert event.data == {"order_id": str(order_id), "user_id": str(user_id)}


async def test_in_memory_publisher_captures_events() -> None:
    publisher = InMemoryEventPublisher()
    event = DomainEvent(event_type="Something", data={})
    await publisher.publish(event)
    assert publisher.events == [event]


async def test_multi_event_publisher_publishes_to_every_wrapped_publisher() -> None:
    a, b = InMemoryEventPublisher(), InMemoryEventPublisher()
    multi = MultiEventPublisher([a, b])
    event = DomainEvent(event_type="Something", data={})

    await multi.publish(event)

    assert a.events == [event]
    assert b.events == [event]


async def test_multi_event_publisher_attempts_every_sink_even_if_one_fails() -> None:
    class FailingPublisher:
        async def publish(self, event: DomainEvent) -> None:
            raise RuntimeError("broker unreachable")

    ok = InMemoryEventPublisher()
    multi = MultiEventPublisher([FailingPublisher(), ok])
    event = DomainEvent(event_type="Something", data={})

    with pytest.raises(ExceptionGroup) as excinfo:
        await multi.publish(event)

    assert ok.events == [event]  # still delivered, despite the other sink failing
    assert len(excinfo.value.exceptions) == 1
    assert isinstance(excinfo.value.exceptions[0], RuntimeError)


async def test_multi_event_publisher_with_no_failures_raises_nothing() -> None:
    multi = MultiEventPublisher([InMemoryEventPublisher()])
    await multi.publish(DomainEvent(event_type="Something", data={}))  # must not raise
