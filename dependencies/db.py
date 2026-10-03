from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppException


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide one session per request.

    Transaction boundaries are owned by the service layer (explicit commit); a session
    that is not committed is rolled back when it closes.
    """
    factory: async_sessionmaker[AsyncSession] | None = request.app.state.session_factory
    if factory is None:
        raise AppException("Service unavailable", code="SERVICE_UNAVAILABLE", status_code=503)
    async with factory() as session:
        yield session
