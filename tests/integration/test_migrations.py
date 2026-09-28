from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.database import Base

ROOT = Path(__file__).resolve().parents[2]


def _config(connection: Connection) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def _upgrade(connection: Connection) -> None:
    command.upgrade(_config(connection), "head")


def _downgrade(connection: Connection) -> None:
    command.downgrade(_config(connection), "base")


def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def _diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, Base.metadata))


async def test_upgrade_matches_models_and_downgrade_removes_tables(
    clean_engine: AsyncEngine,
) -> None:
    async with clean_engine.begin() as connection:
        await connection.run_sync(_upgrade)
    async with clean_engine.connect() as connection:
        assert "users" in await connection.run_sync(_table_names)
        # Migrations and ORM models must not drift apart.
        assert await connection.run_sync(_diff) == []

    async with clean_engine.begin() as connection:
        await connection.run_sync(_downgrade)
    async with clean_engine.connect() as connection:
        assert "users" not in await connection.run_sync(_table_names)
