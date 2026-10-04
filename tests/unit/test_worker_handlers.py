import logging

from worker.handlers import HANDLERS, handle_order_created


async def test_order_created_is_registered() -> None:
    assert HANDLERS["OrderCreated"] is handle_order_created


async def test_handle_order_created_logs_the_order_and_user(
    caplog: logging.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="worker.handlers"):
        await handle_order_created({"data": {"order_id": "order-1", "user_id": "user-1"}})
    assert any("OrderCreated" in record.message for record in caplog.records)


async def test_handle_order_created_tolerates_missing_data() -> None:
    await handle_order_created({})  # must not raise
