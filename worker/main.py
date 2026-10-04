"""Worker entrypoint: `python -m worker.main`. Requires SQS_QUEUE_URL to be set."""

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.logging import configure_logging
from worker.consumer import Worker
from worker.idempotency import InMemoryProcessedEventTracker

logger = logging.getLogger("worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.sqs_queue_url:
        raise RuntimeError("SQS_QUEUE_URL must be set to run the worker")

    worker = Worker(settings.sqs_queue_url, settings.aws_region, InMemoryProcessedEventTracker())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.request_shutdown)

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
