from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from tests.e2e.helpers import admin_client
from tests.unit.sqs_helpers import create_test_queue


@pytest.fixture
def aws() -> Iterator[None]:
    """A mocked AWS for the whole test. The mock is process-wide, so it covers the application's
    boto3 calls (made in worker threads) and the worker's own."""
    with mock_aws():
        yield


@pytest.fixture
def order_queue_url(aws: None) -> str:
    return create_test_queue("order-events")


@pytest.fixture
async def e2e_client(
    db_settings: Settings, db_engine: AsyncEngine, order_queue_url: str
) -> AsyncIterator[AsyncClient]:
    """The application wired to a real database and a (mocked) SQS queue."""
    settings = db_settings.model_copy(update={"sqs_queue_url": order_queue_url})
    async with admin_client(settings) as client:
        yield client
