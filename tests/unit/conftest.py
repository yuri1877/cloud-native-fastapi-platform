"""In-memory fakes so service logic is unit-tested without a database."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.order import Order, OrderStatus
from app.models.user import User
from app.services.order_service import OrderService
from app.services.user_service import UserService


def _integrity_error() -> IntegrityError:
    return IntegrityError("stmt", {}, Exception("constraint violated"))


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeUserRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, User] = {}
        self.fail_add = False
        self.fail_update = False
        self.fail_delete = False

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self.items.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items.values() if u.email == email), None)

    async def list_page(self, *, limit: int, offset: int) -> tuple[Sequence[User], int]:
        ordered = sorted(self.items.values(), key=lambda u: (u.created_at, u.id))
        return ordered[offset : offset + limit], len(ordered)

    async def add(self, user: User) -> User:
        if self.fail_add:
            raise _integrity_error()
        now = datetime.now(UTC)
        user.id = user.id or uuid.uuid4()
        user.created_at = user.updated_at = now
        self.items[user.id] = user
        return user

    async def update(self, user: User, changes: Mapping[str, Any]) -> User:
        if self.fail_update:
            raise _integrity_error()
        for field, value in changes.items():
            setattr(user, field, value)
        return user

    async def delete(self, user: User) -> None:
        if self.fail_delete:
            raise _integrity_error()
        del self.items[user.id]


class FakeOrderRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Order] = {}
        self.fail_add = False

    async def get(self, order_id: uuid.UUID) -> Order | None:
        return self.items.get(order_id)

    async def list_page(
        self,
        *,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
        status: OrderStatus | None = None,
    ) -> tuple[Sequence[Order], int]:
        rows = [
            o
            for o in self.items.values()
            if (user_id is None or o.user_id == user_id) and (status is None or o.status == status)
        ]
        rows.sort(key=lambda o: (o.created_at, o.id))
        return rows[offset : offset + limit], len(rows)

    async def add(self, order: Order) -> Order:
        if self.fail_add:
            raise _integrity_error()
        now = datetime.now(UTC)
        order.id = order.id or uuid.uuid4()
        order.created_at = order.updated_at = now
        self.items[order.id] = order
        return order

    async def update(self, order: Order, changes: Mapping[str, Any]) -> Order:
        for field, value in changes.items():
            setattr(order, field, value)
        return order

    async def delete(self, order: Order) -> None:
        del self.items[order.id]


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def users_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def orders_repo() -> FakeOrderRepository:
    return FakeOrderRepository()


@pytest.fixture
def user_service(session: FakeSession, users_repo: FakeUserRepository) -> UserService:
    return UserService(session, users_repo)  # type: ignore[arg-type]


@pytest.fixture
def order_service(
    session: FakeSession, orders_repo: FakeOrderRepository, users_repo: FakeUserRepository
) -> OrderService:
    return OrderService(session, orders_repo, users_repo)  # type: ignore[arg-type]
