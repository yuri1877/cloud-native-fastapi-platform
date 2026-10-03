"""SQLAlchemy declarative base, async engine factory and readiness probe."""

import asyncio
import logging

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Deterministic constraint names make Alembic migrations reproducible across environments.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine with connection pooling. Does not connect until first use."""
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is not configured")
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        echo=settings.db_echo,
    )


async def check_database(engine: AsyncEngine, timeout: float = 2.0) -> bool:
    """Return True if a trivial query succeeds within ``timeout`` seconds."""
    try:
        async with asyncio.timeout(timeout), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # Log only the exception type: driver messages can contain connection details.
        logger.warning("Database readiness check failed: %s", type(exc).__name__)
        return False
    return True
