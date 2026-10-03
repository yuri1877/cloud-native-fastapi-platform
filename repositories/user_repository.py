import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Persistence only. Flushes but never commits: the service layer owns transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_page(self, *, limit: int, offset: int) -> tuple[Sequence[User], int]:
        stmt = select(User).order_by(User.created_at, User.id).limit(limit).offset(offset)
        items = (await self._session.execute(stmt)).scalars().all()
        total = (await self._session.execute(select(func.count()).select_from(User))).scalar_one()
        return items, total

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)  # load server-generated defaults
        return user

    async def update(self, user: User, changes: Mapping[str, Any]) -> User:
        for field, value in changes.items():
            setattr(user, field, value)
        await self._session.flush()
        await self._session.refresh(user)  # load server-side updated_at
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()
