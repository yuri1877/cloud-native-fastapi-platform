from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_session
from app.dependencies.events import EventPublisherDep
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository
from app.services.order_service import OrderService
from app.services.user_service import UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session, UserRepository(session))


def get_order_service(session: SessionDep, events: EventPublisherDep) -> OrderService:
    return OrderService(session, OrderRepository(session), UserRepository(session), events)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
