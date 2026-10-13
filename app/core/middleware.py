"""Request correlation, access logging, HTTP metrics and tracing middleware.

Flow: read X-Request-ID if present and safely formatted, otherwise generate one; attach it
to request-scoped context (state + contextvar) so it reaches logs and error responses; open a
server span; return the ID on the response; log one structured line per request and record
its metrics.

Unhandled exceptions are the exception to "return it on the response": Starlette's
ServerErrorMiddleware sits *outside* user middleware, so the 500 it produces never passes
back through here. The header is therefore also added where error responses are built
(`app/core/exceptions.py`), and this middleware still records the request before re-raising.
The same goes for the trace ID on that error's log line: the span has ended by then, so the
IDs are also kept as a request-level fallback (`remember_trace`).
"""

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import HTTP_METHODS, Metrics
from app.core.request_context import (
    REQUEST_ID_HEADER,
    generate_request_id,
    is_safe_request_id,
    set_request_id,
    set_span_id,
    set_trace_id,
)
from app.core.tracing import extract_trace_context, mark_span_error, remember_trace, tracer

UNMATCHED_ROUTE = "unmatched"

# Probes and scrapes arrive every few seconds from every pod; tracing them would bury the
# real traffic. They are still logged and counted.
UNTRACED_PATHS = frozenset({"/metrics", "/health/live", "/health/ready"})

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


def _route_label(request: Request) -> str | None:
    """The matched route's template, or None if no route matched (a 404).

    FastAPI puts the matched route in the ASGI scope; a request that matched nothing has none
    and is reported as "unmatched" rather than as its arbitrary, attacker-chosen path.
    """
    if request.scope.get("route") is None:
        return None
    return route_template(request.url.path, request.scope.get("path_params") or {})


def _method_label(method: str) -> str:
    return method if method in HTTP_METHODS else "_OTHER"


def _parent_context(request: Request) -> Context:
    """Where the server span's trace comes from.

    By default every request starts a fresh trace. An inbound `traceparent` is honoured only
    when `TRACING_TRUST_INBOUND_CONTEXT` is set, because a caller who can choose our trace ID
    and sampling flag can also force every one of its requests to be sampled.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and settings.tracing_trust_inbound_context:
        return extract_trace_context(dict(request.headers))
    return Context()


def _finish_span(
    span: Span, method: str, route: str | None, status_code: int, error: BaseException | None
) -> None:
    span.set_attribute("http.response.status_code", status_code)
    label = _method_label(method)
    if route is None:
        span.update_name(label)
    else:
        span.set_attribute("http.route", route)
        span.update_name(f"{label} {route}")
    if error is not None:
        mark_span_error(span, error)
    elif status_code >= 500:
        span.set_status(Status(StatusCode.ERROR))


def _record_request(request: Request, status_code: int, start: float, route: str | None) -> None:
    """Log the request and record its metrics, both from the same duration and route."""
    duration = time.perf_counter() - start
    route_label = route or UNMATCHED_ROUTE
    # `path` is the raw path (no query string, which can carry tokens) for debugging.
    logger.log(
        logging.ERROR if status_code >= 500 else logging.INFO,
        "request completed",
        extra={
            "method": request.method,
            "route": route_label,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
        },
    )

    metrics: Metrics | None = getattr(request.app.state, "metrics", None)
    if metrics is None:
        return
    try:
        metrics.observe_request(
            method=request.method,
            route=route_label,
            status_code=status_code,
            duration_seconds=duration,
        )
    except Exception:
        # Observability must never fail a request, or mask the real error of one that is
        # already failing.
        logger.exception("Failed to record request metrics")


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
        # Start each request with no trace fallback, so an untraced request (a probe) cannot
        # inherit the previous request's IDs where requests share a task, as in tests.
        set_trace_id(None)
        set_span_id(None)

        start = time.perf_counter()
        if request.url.path in UNTRACED_PATHS:
            return await self._handle(request, call_next, request_id, start, None)

        with tracer.start_as_current_span(
            _method_label(request.method),
            context=_parent_context(request),
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": _method_label(request.method),
                "url.path": request.url.path,
                "app.request_id": request_id,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            remember_trace(span)
            return await self._handle(request, call_next, request_id, start, span)

    async def _handle(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        request_id: str,
        start: float,
        span: Span | None,
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:
            route = _route_label(request)
            if span is not None:
                _finish_span(span, request.method, route, 500, exc)
            _record_request(request, 500, start, route)
            raise

        route = _route_label(request)
        if span is not None:
            _finish_span(span, request.method, route, response.status_code, None)
        response.headers[REQUEST_ID_HEADER] = request_id
        _record_request(request, response.status_code, start, route)
        return response
