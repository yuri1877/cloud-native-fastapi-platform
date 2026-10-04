"""Order domain events."""

import uuid

from app.events.base import DomainEvent


def order_created_event(*, order_id: uuid.UUID, user_id: uuid.UUID) -> DomainEvent:
    return DomainEvent(
        event_type="OrderCreated",
        data={"order_id": str(order_id), "user_id": str(user_id)},
    )
