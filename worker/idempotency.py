"""Idempotency tracking for the SQS worker.

In-memory only: a processed-event record is lost on worker restart, so a message
redelivered after a restart could be reprocessed. Acceptable for this portfolio's scope; a
durable store (a database table, or DynamoDB with a TTL) is the natural production upgrade,
matching the purpose of `event_id` (app/events/base.py) - noted here rather than silently
assumed to be solved.
"""

from typing import Protocol


class ProcessedEventTracker(Protocol):
    async def already_processed(self, event_id: str) -> bool: ...
    async def mark_processed(self, event_id: str) -> None: ...


class InMemoryProcessedEventTracker:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def already_processed(self, event_id: str) -> bool:
        return event_id in self._seen

    async def mark_processed(self, event_id: str) -> None:
        self._seen.add(event_id)
