"""EventBridge implementation of the EventPublisher protocol (app/events/base.py).

EventBridge is used for event *routing* - selected domain events become available for
other consumers/integrations to subscribe to via EventBridge rules - distinct from SQS's
role as the durable work queue the app's own worker consumes. See ADR-004 for the boundary
between the two.
"""

import asyncio
from typing import TYPE_CHECKING

import boto3

from app.events.base import DomainEvent

if TYPE_CHECKING:
    from mypy_boto3_events.client import EventBridgeClient


class EventBridgeEventPublisher:
    def __init__(self, event_bus_name: str, region_name: str) -> None:
        self._event_bus_name = event_bus_name
        # Constructing a client does not open a connection; no network call happens here.
        self._client: EventBridgeClient = boto3.client("events", region_name=region_name)

    async def publish(self, event: DomainEvent) -> None:
        await asyncio.to_thread(self._send, event)

    def _send(self, event: DomainEvent) -> None:
        response = self._client.put_events(
            Entries=[
                {
                    "EventBusName": self._event_bus_name,
                    "Source": event.source,
                    "DetailType": event.event_type,
                    "Detail": event.model_dump_json(),
                }
            ]
        )
        # put_events doesn't raise on a per-entry failure; FailedEntryCount must be
        # checked explicitly so a rejected event surfaces the same way an SQS failure does.
        if response.get("FailedEntryCount", 0) > 0:
            entry = response["Entries"][0]
            raise RuntimeError(
                f"EventBridge rejected the event: "
                f"{entry.get('ErrorCode')} {entry.get('ErrorMessage')}"
            )
