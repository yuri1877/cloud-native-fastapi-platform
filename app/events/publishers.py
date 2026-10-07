"""In-process EventPublisher implementations.

Real infrastructure adapters (SQS in Phase 12, EventBridge in Phase 13) implement the same
`EventPublisher` protocol, so adding or swapping one touches app wiring only - never the
service layer that calls `publish()`.
"""

import logging
from collections.abc import Sequence

from app.events.base import DomainEvent, EventPublisher

logger = logging.getLogger("app.events")


class LoggingEventPublisher:
    """Default publisher: logs the event as structured data. Used when nothing else is
    configured; safe to keep running alongside a real sink later as a debugging aid."""

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


class MultiEventPublisher:
    """Publishes to every wrapped publisher - used when more than one sink is configured
    (SQS for the worker's queue, EventBridge for routing/integration; see ADR-004), so
    OrderService still only ever depends on a single EventPublisher.

    Every publisher gets an independent attempt: one sink failing does not stop the event
    reaching the others. Any failures are collected and raised together afterwards.
    """

    def __init__(self, publishers: Sequence[EventPublisher]) -> None:
        self._publishers = publishers

    async def publish(self, event: DomainEvent) -> None:
        errors: list[Exception] = []
        for publisher in self._publishers:
            try:
                await publisher.publish(event)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Failed to publish to one or more event sinks", errors)
