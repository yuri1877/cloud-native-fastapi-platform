from typing import Annotated

from fastapi import Depends, Request

from app.events.base import EventPublisher


def get_event_publisher(request: Request) -> EventPublisher:
    return request.app.state.event_publisher  # type: ignore[no-any-return]


EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]
