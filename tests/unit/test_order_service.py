import uuid

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.events.publishers import InMemoryEventPublisher
from app.models.order import OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.schemas.user import UserCreate
from app.services.order_service import OrderService
from app.services.user_service import UserService
from tests.unit.conftest import FakeOrderRepository, FakeSession, FakeUserRepository


async def _user(user_service: UserService) -> uuid.UUID:
    return (await user_service.create_user(UserCreate(email="a@example.com", name="A"))).id


async def _order(
    order_service: OrderService, user_id: uuid.UUID, status: OrderStatus = OrderStatus.PENDING
) -> uuid.UUID:
    order = await order_service.create_order(
        OrderCreate(user_id=user_id, total_amount=1000, currency="GBP")
    )
    if status != OrderStatus.PENDING:
        order.status = status  # arrange state directly
    return order.id


async def test_create_order_starts_pending(
    order_service: OrderService, user_service: UserService
) -> None:
    user_id = await _user(user_service)
    order = await order_service.create_order(
        OrderCreate(user_id=user_id, total_amount=1999, currency="GBP")
    )
    assert order.status == OrderStatus.PENDING
    assert (order.total_amount, order.currency) == (1999, "GBP")


async def test_create_order_for_unknown_user(order_service: OrderService) -> None:
    with pytest.raises(NotFoundException) as excinfo:
        await order_service.create_order(
            OrderCreate(user_id=uuid.uuid4(), total_amount=100, currency="GBP")
        )
    assert excinfo.value.code == "USER_NOT_FOUND"


async def test_create_order_fk_race_maps_to_user_not_found(
    order_service: OrderService,
    user_service: UserService,
    orders_repo: FakeOrderRepository,
    session: FakeSession,
) -> None:
    user_id = await _user(user_service)
    orders_repo.fail_add = True
    with pytest.raises(NotFoundException) as excinfo:
        await order_service.create_order(
            OrderCreate(user_id=user_id, total_amount=100, currency="GBP")
        )
    assert excinfo.value.code == "USER_NOT_FOUND"
    assert session.rollbacks == 1


async def test_get_order_not_found(order_service: OrderService) -> None:
    with pytest.raises(NotFoundException) as excinfo:
        await order_service.get_order(uuid.uuid4())
    assert excinfo.value.code == "ORDER_NOT_FOUND"


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.PENDING, OrderStatus.PROCESSING),
        (OrderStatus.PENDING, OrderStatus.CANCELLED),
        (OrderStatus.PROCESSING, OrderStatus.COMPLETED),
        (OrderStatus.PROCESSING, OrderStatus.CANCELLED),
    ],
)
async def test_valid_status_transitions(
    order_service: OrderService,
    user_service: UserService,
    current: OrderStatus,
    target: OrderStatus,
) -> None:
    order_id = await _order(order_service, await _user(user_service), current)
    updated = await order_service.update_order(order_id, OrderUpdate(status=target))
    assert updated.status == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.PENDING, OrderStatus.COMPLETED),
        (OrderStatus.PROCESSING, OrderStatus.PENDING),
        (OrderStatus.COMPLETED, OrderStatus.CANCELLED),
        (OrderStatus.CANCELLED, OrderStatus.PROCESSING),
    ],
)
async def test_invalid_status_transitions(
    order_service: OrderService,
    user_service: UserService,
    current: OrderStatus,
    target: OrderStatus,
) -> None:
    order_id = await _order(order_service, await _user(user_service), current)
    with pytest.raises(ConflictException) as excinfo:
        await order_service.update_order(order_id, OrderUpdate(status=target))
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"


async def test_amount_editable_only_while_pending(
    order_service: OrderService, user_service: UserService
) -> None:
    user_id = await _user(user_service)
    pending = await _order(order_service, user_id)
    updated = await order_service.update_order(pending, OrderUpdate(total_amount=2500))
    assert updated.total_amount == 2500

    processing = await _order(order_service, user_id, OrderStatus.PROCESSING)
    with pytest.raises(ConflictException) as excinfo:
        await order_service.update_order(processing, OrderUpdate(currency="USD"))
    assert excinfo.value.code == "ORDER_NOT_MODIFIABLE"


@pytest.mark.parametrize(
    ("status", "deletable"),
    [
        (OrderStatus.PENDING, True),
        (OrderStatus.CANCELLED, True),
        (OrderStatus.PROCESSING, False),
        (OrderStatus.COMPLETED, False),
    ],
)
async def test_delete_rules(
    order_service: OrderService,
    user_service: UserService,
    orders_repo: FakeOrderRepository,
    status: OrderStatus,
    deletable: bool,
) -> None:
    order_id = await _order(order_service, await _user(user_service), status)
    if deletable:
        await order_service.delete_order(order_id)
        assert order_id not in orders_repo.items
    else:
        with pytest.raises(ConflictException) as excinfo:
            await order_service.delete_order(order_id)
        assert excinfo.value.code == "ORDER_NOT_DELETABLE"


async def test_list_orders_filters(order_service: OrderService, user_service: UserService) -> None:
    user_id = await _user(user_service)
    await _order(order_service, user_id)
    await _order(order_service, user_id, OrderStatus.CANCELLED)
    _, total = await order_service.list_orders(limit=10, offset=0, user_id=user_id)
    assert total == 2
    items, total = await order_service.list_orders(limit=10, offset=0, status=OrderStatus.CANCELLED)
    assert total == 1
    assert items[0].status == OrderStatus.CANCELLED


async def test_create_order_publishes_order_created_event(
    order_service: OrderService, user_service: UserService, events: InMemoryEventPublisher
) -> None:
    user_id = await _user(user_service)
    order = await order_service.create_order(
        OrderCreate(user_id=user_id, total_amount=1999, currency="GBP")
    )
    assert len(events.events) == 1
    event = events.events[0]
    assert event.event_type == "OrderCreated"
    assert event.data == {"order_id": str(order.id), "user_id": str(user_id)}


async def test_no_event_published_when_order_creation_fails(
    order_service: OrderService, events: InMemoryEventPublisher
) -> None:
    with pytest.raises(NotFoundException):
        await order_service.create_order(
            OrderCreate(user_id=uuid.uuid4(), total_amount=100, currency="GBP")
        )
    assert events.events == []


async def test_event_publish_failure_does_not_fail_order_creation(
    session: FakeSession,
    orders_repo: FakeOrderRepository,
    users_repo: FakeUserRepository,
    user_service: UserService,
) -> None:
    class FailingPublisher:
        async def publish(self, event: object) -> None:
            raise RuntimeError("broker is unreachable")

    user_id = await _user(user_service)  # shares `users_repo` with the service under test
    service = OrderService(  # type: ignore[arg-type]
        session, orders_repo, users_repo, FailingPublisher()
    )
    order = await service.create_order(
        OrderCreate(user_id=user_id, total_amount=500, currency="GBP")
    )
    assert order.id is not None  # the order was still created despite the publish failure
