from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory. ``expire_on_commit=False`` avoids implicit lazy loads after commit,
    which are not allowed in async code."""
    return async_sessionmaker(engine, expire_on_commit=False)
