"""Request correlation middleware.

Flow: read X-Request-ID if present and safely formatted, otherwise generate one; attach it
to request-scoped context (state + contextvar) so it reaches logs and error responses;
return it on every response, including ones raised by later middleware/handlers.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import (
    generate_request_id,
    is_safe_request_id,
    set_request_id,
)

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER)
        request_id = inbound if inbound and is_safe_request_id(inbound) else generate_request_id()

        request.state.request_id = request_id
        set_request_id(request_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request completed",
            extra={
                "http_method": request.method,
                "http_route": request.url.path,
                "http_status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
