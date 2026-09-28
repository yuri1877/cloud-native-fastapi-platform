import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


def _email_conflict() -> ConflictException:
    return ConflictException("A user with this email already exists", code="EMAIL_ALREADY_EXISTS")


class UserService:
    """Business rules and transaction boundaries for users."""

    def __init__(self, session: AsyncSession, users: UserRepository) -> None:
        self._session = session
        self._users = users

    async def list_users(self, *, limit: int, offset: int) -> tuple[Sequence[User], int]:
        return await self._users.list_page(limit=limit, offset=offset)

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundException("User was not found", code="USER_NOT_FOUND")
        return user

    async def create_user(self, data: UserCreate) -> User:
        if await self._users.get_by_email(data.email) is not None:
            raise _email_conflict()
        try:
            user = await self._users.add(User(email=data.email, name=data.name))
            await self._session.commit()
        except IntegrityError as exc:
            # Lost a race with a concurrent request; the unique constraint is the final arbiter.
            await self._session.rollback()
            raise _email_conflict() from exc
        return user

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        changes = data.model_dump(exclude_unset=True)

        new_email = changes.get("email")
        if new_email is not None and new_email != user.email:
            existing = await self._users.get_by_email(new_email)
            if existing is not None and existing.id != user.id:
                raise _email_conflict()

        try:
            user = await self._users.update(user, changes)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _email_conflict() from exc
        return user

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self.get_user(user_id)
        try:
            await self._users.delete(user)
            await self._session.commit()
        except IntegrityError as exc:
            # orders.user_id is ON DELETE RESTRICT: users with orders cannot be deleted.
            await self._session.rollback()
            raise ConflictException(
                "User has orders and cannot be deleted", code="USER_HAS_ORDERS"
            ) from exc
