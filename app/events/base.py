"""Domain event envelope and publisher abstraction.

Events are the platform's integration contract for asynchronous processing (SQS in Phase 12,
EventBridge in Phase 13). Business logic depends only on this abstraction, never on an AWS
SDK directly - see ADR-004 once the SQS/EventBridge boundary is documented.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

EVENT_VERSION = "1"


class DomainEvent(BaseModel):
    """Envelope every domain event shares; `data` carries the event-specific payload.

    - `event_id` supports idempotent processing downstream (a consumer de-duplicates on it).
    - `event_version` lets the payload shape evolve without breaking old consumers.
    - `occurred_at` is when the fact became true in the domain, not when it was published.
    - Immutable (`frozen`): an event is a record of something that already happened.
    """

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    event_version: str = EVENT_VERSION
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "order-service"
    data: dict[str, Any]


class EventPublisher(Protocol):
    """Infrastructure-specific implementations (SQS, EventBridge) satisfy this interface;
    service-layer code depends only on this Protocol, never on a specific broker's SDK."""

    async def publish(self, event: DomainEvent) -> None: ...
