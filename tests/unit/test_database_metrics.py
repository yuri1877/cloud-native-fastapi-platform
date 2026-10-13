"""The statement-timing hooks, exercised against an in-memory SQLite engine (no Postgres
needed). The asyncpg path is covered by the integration test against a real database."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.metrics import START_TIMES_KEY, Metrics, attach_database_metrics


def _count(metrics: Metrics, operation: str) -> float:
    value = metrics.registry.get_sample_value(
        "database_operation_duration_seconds_count", {"operation": operation}
    )
    return value or 0.0


@pytest.fixture
def instrumented() -> Iterator[tuple[Engine, Metrics]]:
    metrics = Metrics()
    engine = create_engine("sqlite://")
    with engine.connect():
        pass  # first connect runs dialect initialisation; keep that out of the counts
    attach_database_metrics(engine, metrics)
    yield engine, metrics
    engine.dispose()


def test_each_statement_kind_is_timed_under_its_own_label(
    instrumented: tuple[Engine, Metrics],
) -> None:
    engine, metrics = instrumented
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO t (name) VALUES ('a')"))
        conn.execute(text("SELECT * FROM t"))
        conn.execute(text("UPDATE t SET name = 'b'"))
        conn.execute(text("DELETE FROM t"))

    assert _count(metrics, "INSERT") == 1.0
    assert _count(metrics, "SELECT") == 1.0
    assert _count(metrics, "UPDATE") == 1.0
    assert _count(metrics, "DELETE") == 1.0
    assert _count(metrics, "OTHER") >= 1.0  # the CREATE TABLE


def test_a_failing_statement_is_still_timed_and_leaves_no_stale_state(
    instrumented: tuple[Engine, Metrics],
) -> None:
    engine, metrics = instrumented
    with engine.connect() as conn:
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT * FROM does_not_exist"))
        conn.rollback()

        assert _count(metrics, "SELECT") == 1.0
        assert conn.info[START_TIMES_KEY] == []

        conn.execute(text("SELECT 1"))
        assert _count(metrics, "SELECT") == 2.0
        assert conn.info[START_TIMES_KEY] == []


def test_durations_are_recorded_as_non_negative_seconds(
    instrumented: tuple[Engine, Metrics],
) -> None:
    engine, metrics = instrumented
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    total = metrics.registry.get_sample_value(
        "database_operation_duration_seconds_sum", {"operation": "SELECT"}
    )
    assert total is not None
    assert total >= 0
