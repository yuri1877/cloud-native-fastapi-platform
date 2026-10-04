"""Confirms the full wiring: creating an order via the real API publishes an OrderCreated
event through the app's EventPublisher dependency."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.dependencies.auth import get_token_verifier
from app.dependencies.events import get_event_publisher
from app.events.publishers import InMemoryEventPublisher
from app.main import create_app
from tests.unit.auth_helpers import FakeTokenVerifier, make_token


@pytest.fixture
def events_publisher() -> InMemoryEventPublisher:
    return InMemoryEventPublisher()


@pytest.fixture
async def events_client(
    db_settings: Settings, db_engine: AsyncEngine, events_publisher: InMemoryEventPublisher
) -> AsyncIterator[AsyncClient]:
    app = create_app(db_settings)
    app.dependency_overrides[get_token_verifier] = FakeTokenVerifier
    app.dependency_overrides[get_event_publisher] = lambda: events_publisher
    token = make_token(subject="admin-test-user", roles=["admin"])
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client


async def test_creating_an_order_publishes_order_created(
    events_client: AsyncClient, events_publisher: InMemoryEventPublisher
) -> None:
    user = await events_client.post(
        "/api/v1/users", json={"email": "events@example.com", "name": "A"}
    )
    assert user.status_code == 201
    order = await events_client.post(
        "/api/v1/orders",
        json={"user_id": user.json()["id"], "total_amount": 500, "currency": "GBP"},
    )
    assert order.status_code == 201

    assert len(events_publisher.events) == 1
    event = events_publisher.events[0]
    assert event.event_type == "OrderCreated"
    assert event.data == {"order_id": order.json()["id"], "user_id": user.json()["id"]}
