import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.order import Order, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository
from app.schemas.order import OrderCreate, OrderUpdate

# Order lifecycle. COMPLETED and CANCELLED are terminal.
ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}
DELETABLE_STATUSES = frozenset({OrderStatus.PENDING, OrderStatus.CANCELLED})


def _user_not_found() -> NotFoundException:
    return NotFoundException("User was not found", code="USER_NOT_FOUND")


class OrderService:
    """Business rules and transaction boundaries for orders."""

    def __init__(
        self, session: AsyncSession, orders: OrderRepository, users: UserRepository
    ) -> None:
        self._session = session
        self._orders = orders
        self._users = users

    async def list_orders(
        self,
        *,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
        status: OrderStatus | None = None,
    ) -> tuple[Sequence[Order], int]:
        return await self._orders.list_page(
            limit=limit, offset=offset, user_id=user_id, status=status
        )

    async def get_order(self, order_id: uuid.UUID) -> Order:
        order = await self._orders.get(order_id)
        if order is None:
            raise NotFoundException("Order was not found", code="ORDER_NOT_FOUND")
        return order

    async def create_order(self, data: OrderCreate) -> Order:
        if await self._users.get(data.user_id) is None:
            raise _user_not_found()
        order = Order(
            user_id=data.user_id,
            status=OrderStatus.PENDING,
            total_amount=data.total_amount,
            currency=data.currency,
        )
        try:
            order = await self._orders.add(order)
            await self._session.commit()
        except IntegrityError as exc:
            # The user was deleted between the check and the insert (foreign key violation).
            await self._session.rollback()
            raise _user_not_found() from exc
        return order

    async def update_order(self, order_id: uuid.UUID, data: OrderUpdate) -> Order:
        order = await self.get_order(order_id)
        changes = data.model_dump(exclude_unset=True)

        new_status = changes.get("status")
        if new_status is not None and new_status != order.status:
            if new_status not in ALLOWED_TRANSITIONS[order.status]:
                raise ConflictException(
                    f"Cannot change order status from {order.status} to {new_status}",
                    code="INVALID_STATUS_TRANSITION",
                )
        # Amount and currency are only editable while the order has not started processing.
        if ("total_amount" in changes or "currency" in changes) and (
            order.status != OrderStatus.PENDING
        ):
            raise ConflictException(
                "Amount and currency can only be changed while the order is PENDING",
                code="ORDER_NOT_MODIFIABLE",
            )

        order = await self._orders.update(order, changes)
        await self._session.commit()
        return order

    async def delete_order(self, order_id: uuid.UUID) -> None:
        order = await self.get_order(order_id)
        if order.status not in DELETABLE_STATUSES:
            raise ConflictException(
                "Only PENDING or CANCELLED orders can be deleted", code="ORDER_NOT_DELETABLE"
            )
        await self._orders.delete(order)
        await self._session.commit()
