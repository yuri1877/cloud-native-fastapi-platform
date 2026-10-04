"""Business processing for each event type.

Deliberately simple for this portfolio (a structured log line per event); a real handler
would update a read model, send a notification, trigger a downstream workflow, etc. Add a
new event type by adding an entry to HANDLERS.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("worker.handlers")

Handler = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_order_created(payload: dict[str, Any]) -> None:
    data = payload.get("data", {})
    logger.info(
        "Processing OrderCreated",
        extra={"order_id": data.get("order_id"), "user_id": data.get("user_id")},
    )


HANDLERS: dict[str, Handler] = {
    "OrderCreated": handle_order_created,
}
