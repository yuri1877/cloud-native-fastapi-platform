"""In-process EventPublisher implementations.

Real infrastructure adapters (SQS in Phase 12, EventBridge in Phase 13) implement the same
`EventPublisher` protocol, so swapping one in later touches app wiring only - never the
service layer that calls `publish()`.
"""

import logging

from app.events.base import DomainEvent

logger = logging.getLogger("app.events")


class LoggingEventPublisher:
    """Default publisher: logs the event as structured data. Used in every environment
    until Phase 12 adds a real queue adapter; safe to keep running alongside one later as
    a secondary sink if that's ever useful for debugging."""

    async def publish(self, event: DomainEvent) -> None:
        logger.info(
            "domain event published",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "event_version": event.event_version,
            },
        )


class InMemoryEventPublisher:
    """Captures published events in a list instead of sending them anywhere. Used by tests
    to assert on publish behaviour without a real broker."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
