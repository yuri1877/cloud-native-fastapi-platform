import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.security import TokenVerifier, create_token_verifier
from app.db.database import create_engine
from app.db.session import create_session_factory
from app.events.base import EventPublisher
from app.events.eventbridge import EventBridgeEventPublisher
from app.events.publishers import LoggingEventPublisher, MultiEventPublisher
from app.events.sqs import SQSEventPublisher

logger = logging.getLogger(__name__)


def _build_event_publisher(settings: Settings) -> EventPublisher:
    """SQS (work queue) and EventBridge (routing) are independent, optional sinks - see
    ADR-004. Zero, one, or both may be configured; OrderService always sees a single
    EventPublisher regardless of how many are active."""
    publishers: list[EventPublisher] = []
    if settings.sqs_queue_url:
        publishers.append(SQSEventPublisher(settings.sqs_queue_url, settings.aws_region))
    if settings.eventbridge_bus_name:
        publishers.append(
            EventBridgeEventPublisher(settings.eventbridge_bus_name, settings.aws_region)
        )

    if len(publishers) > 1:
        return MultiEventPublisher(publishers)
    if publishers:
        return publishers[0]
    return LoggingEventPublisher()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # Creating the engine does not open a connection, so it is safe to do here.
    engine = create_engine(settings) if settings.database_url is not None else None
    token_verifier: TokenVerifier | None = (
        create_token_verifier(settings.oidc_jwks_url) if settings.oidc_jwks_url else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings)
        logger.info("Application starting")
        yield
        logger.info("Application stopping")
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="Cloud-Native FastAPI Platform",
        summary="Users and orders API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine) if engine is not None else None
    app.state.token_verifier = token_verifier
    app.state.event_publisher = _build_event_publisher(settings)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
