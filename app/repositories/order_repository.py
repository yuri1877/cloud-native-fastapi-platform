import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus


class OrderRepository:
    """Persistence only. Flushes but never commits: the service layer owns transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: uuid.UUID) -> Order | None:
        return await self._session.get(Order, order_id)

    async def list_page(
        self,
        *,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
        status: OrderStatus | None = None,
    ) -> tuple[Sequence[Order], int]:
        conditions: list[ColumnElement[bool]] = []
        if user_id is not None:
            conditions.append(Order.user_id == user_id)
        if status is not None:
            conditions.append(Order.status == status)

        stmt = (
            select(Order)
            .where(*conditions)
            .order_by(Order.created_at, Order.id)
            .limit(limit)
            .offset(offset)
        )
        items = (await self._session.execute(stmt)).scalars().all()
        count_stmt = select(func.count()).select_from(Order).where(*conditions)
        total = (await self._session.execute(count_stmt)).scalar_one()
        return items, total

    async def add(self, order: Order) -> Order:
        self._session.add(order)
        await self._session.flush()
        await self._session.refresh(order)
        return order

    async def update(self, order: Order, changes: Mapping[str, Any]) -> Order:
        for field, value in changes.items():
            setattr(order, field, value)
        await self._session.flush()
        await self._session.refresh(order)
        return order

    async def delete(self, order: Order) -> None:
        await self._session.delete(order)
        await self._session.flush()
