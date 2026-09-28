import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import User


async def test_engine_can_query(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1


async def test_user_roundtrip_sets_defaults(db_session: AsyncSession) -> None:
    db_session.add(User(email="a@example.com", name="A"))
    await db_session.commit()

    user = (await db_session.execute(select(User))).scalar_one()
    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None


async def test_email_is_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="dup@example.com", name="One"))
    await db_session.commit()

    db_session.add(User(email="dup@example.com", name="Two"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_uncommitted_changes_are_rolled_back(db_engine: AsyncEngine) -> None:
    from app.db.session import create_session_factory

    factory = create_session_factory(db_engine)
    async with factory() as session:
        session.add(User(email="ghost@example.com", name="Ghost"))
        await session.flush()
    async with factory() as session:
        assert (await session.execute(select(User))).first() is None
