"""A few end-to-end journeys through the whole platform: the real application, a real database,
a mocked SQS queue and the real worker. They are deliberately few; the detail lives in the unit,
integration and contract tests. Needs TEST_DATABASE_URL."""

from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from tests.e2e.helpers import admin_client
from tests.unit.sqs_helpers import REGION, receive_all
from worker.consumer import Worker
from worker.idempotency import InMemoryProcessedEventTracker

pytestmark = pytest.mark.e2e

LogReader = Callable[[], list[dict[str, Any]]]


async def test_an_order_flows_from_the_api_through_sqs_to_the_worker(
    e2e_client: AsyncClient,
    order_queue_url: str,
    spans: InMemorySpanExporter,
    json_logs: LogReader,
) -> None:
    user = await e2e_client.post(
        "/api/v1/users", json={"email": "flow@example.com", "name": "Flow"}
    )
    assert user.status_code == 201
    order = await e2e_client.post(
        "/api/v1/orders",
        json={"user_id": user.json()["id"], "total_amount": 2500, "currency": "GBP"},
    )
    assert order.status_code == 201

    consumer = Worker(order_queue_url, REGION, InMemoryProcessedEventTracker(), wait_time_seconds=0)
    assert await consumer.poll_once() == 1
    assert receive_all(order_queue_url) == []  # consumed and acknowledged

    # One trace spans the API request and the worker's processing of its event...
    finished = spans.get_finished_spans()
    server = next(s for s in finished if s.name == "POST /api/v1/orders")
    process = next(s for s in finished if s.name == "process OrderCreated")
    assert process.context.trace_id == server.context.trace_id

    # ...and the worker's log line says which order it was, under the same trace ID.
    [line] = [entry for entry in json_logs() if entry["logger"] == "worker.handlers"]
    assert line["order_id"] == order.json()["id"]
    assert line["user_id"] == user.json()["id"]
    assert line["trace_id"] == format(server.context.trace_id, "032x")


async def test_the_order_lifecycle_and_referential_integrity(e2e_client: AsyncClient) -> None:
    client = e2e_client
    user = await client.post("/api/v1/users", json={"email": "life@example.com", "name": "Life"})
    user_id = user.json()["id"]
    order = await client.post(
        "/api/v1/orders", json={"user_id": user_id, "total_amount": 1000, "currency": "GBP"}
    )
    order_id = order.json()["id"]
    assert order.json()["status"] == "PENDING"

    # A user with an order cannot be deleted.
    blocked = await client.delete(f"/api/v1/users/{user_id}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "USER_HAS_ORDERS"

    # An order only moves forward, and its amount is frozen once it is processing.
    processing = await client.patch(f"/api/v1/orders/{order_id}", json={"status": "PROCESSING"})
    assert processing.json()["status"] == "PROCESSING"
    backwards = await client.patch(f"/api/v1/orders/{order_id}", json={"status": "PENDING"})
    assert backwards.status_code == 409
    assert backwards.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    frozen = await client.patch(f"/api/v1/orders/{order_id}", json={"total_amount": 1})
    assert frozen.status_code == 409
    assert frozen.json()["error"]["code"] == "ORDER_NOT_MODIFIABLE"

    # A processing order cannot be deleted; a cancelled one can.
    assert (await client.delete(f"/api/v1/orders/{order_id}")).status_code == 409
    cancelled = await client.patch(f"/api/v1/orders/{order_id}", json={"status": "CANCELLED"})
    assert cancelled.status_code == 200
    assert (await client.delete(f"/api/v1/orders/{order_id}")).status_code == 204

    # With its orders gone the user can be deleted, and both are then gone.
    assert (await client.delete(f"/api/v1/users/{user_id}")).status_code == 204
    assert (await client.get(f"/api/v1/users/{user_id}")).status_code == 404
    assert (await client.get(f"/api/v1/orders/{order_id}")).status_code == 404


async def test_an_unavailable_queue_does_not_fail_order_creation(
    db_settings: Settings,
    db_engine: AsyncEngine,
    aws: None,
    spans: InMemorySpanExporter,
    json_logs: LogReader,
) -> None:
    missing_queue = "https://sqs.eu-west-2.amazonaws.com/123456789012/queue-that-does-not-exist"
    settings = db_settings.model_copy(update={"sqs_queue_url": missing_queue})

    async with admin_client(settings) as client:
        user = await client.post(
            "/api/v1/users", json={"email": "queue-down@example.com", "name": "Q"}
        )
        order = await client.post(
            "/api/v1/orders",
            json={"user_id": user.json()["id"], "total_amount": 500, "currency": "GBP"},
        )
        # The order is created and durably stored even though publishing its event failed.
        assert order.status_code == 201
        assert (await client.get(f"/api/v1/orders/{order.json()['id']}")).status_code == 200

    # The failure is visible, not silent: in the logs, and as an error span in the trace.
    failures = [
        entry
        for entry in json_logs()
        if entry["message"].startswith("Failed to publish OrderCreated")
    ]
    assert len(failures) == 1
    assert failures[0]["level"] == "ERROR"
    send = next(s for s in spans.get_finished_spans() if s.name.startswith("send queue-that"))
    assert send.status.status_code == StatusCode.ERROR
