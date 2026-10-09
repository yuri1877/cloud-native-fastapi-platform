"""Request correlation and access logging middleware.

Flow: read X-Request-ID if present and safely formatted, otherwise generate one; attach it
to request-scoped context (state + contextvar) so it reaches logs and error responses;
return it on the response; log one structured line per request.

Unhandled exceptions are the exception to "return it on the response": Starlette's
ServerErrorMiddleware sits *outside* user middleware, so the 500 it produces never passes
back through here. The header is therefore also added where error responses are built
(`app/core/exceptions.py`), and this middleware still logs the request before re-raising.
"""

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import (
    REQUEST_ID_HEADER,
    generate_request_id,
    is_safe_request_id,
    set_request_id,
)

UNMATCHED_ROUTE = "unmatched"

logger = logging.getLogger("app.access")


def route_template(path: str, path_params: Mapping[str, Any]) -> str:
    """Turn a concrete path into its template: /api/v1/users/<uuid> -> /api/v1/users/{user_id}.

    Built from the real request path and the matched path parameters rather than from the
    matched route's own `path`, which can be relative to a router prefix and so omit it.
    Matching is per path segment. Two known limits, both harmless for logging: a parameter
    whose value equals a literal segment would template that segment too, and a multi-segment
    `{name:path}` parameter would not be templated at all (this API has none).
    """
    names_by_value = {str(value): name for name, value in path_params.items()}
    return "/".join(
        "{" + names_by_value[segment] + "}" if segment in names_by_value else segment
        for segment in path.split("/")
    )


def _log_request(request: Request, status_code: int, start: float) -> None:
    # `route` is the matched path *template*, which is bounded and safe to aggregate on. FastAPI
    # puts the matched route in the ASGI scope; a request that matched nothing (404) has none
    # and is logged as "unmatched" rather than as its arbitrary, attacker-chosen path.
    # `path` is the raw path (no query string, which can carry tokens) for debugging.
    matched = request.scope.get("route") is not None
    route = (
        route_template(request.url.path, request.scope.get("path_params") or {})
        if matched
        else UNMATCHED_ROUTE
    )
    logger.log(
        logging.ERROR if status_code >= 500 else logging.INFO,
        "request completed",
        extra={
            "method": request.method,
            "route": route,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER)
        request_id = inbound if inbound and is_safe_request_id(inbound) else generate_request_id()

        request.state.request_id = request_id
        # Deliberately not reset afterwards: on an unhandled exception the error handler
        # runs after this frame unwinds and still needs the ID for its own log line. Each
        # request runs in its own asyncio task under uvicorn, so the value cannot leak
        # across requests.
        set_request_id(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _log_request(request, 500, start)
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        _log_request(request, response.status_code, start)
        return response
