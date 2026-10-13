# Request correlation

## Flow

Incoming request
|
Read X-Request-ID if present and safely formatted
|
Generate one (uuid4 hex) if absent or malformed
|
Attach to request.state and a contextvar (app/core/request_context.py)
|
Included in every structured log line for the request
|
Returned in the X-Request-ID response header


Implemented by `RequestIDMiddleware` in `app/core/middleware.py`, registered first in
`create_app()`.

## Trust model
An inbound `X-Request-ID` is **never treated as a security identity** - it is not used for
authentication, authorization, or audit attribution, only for correlating log lines and
responses belonging to the same request. It must match `^[A-Za-z0-9_-]{8,128}$`
(`app/core/request_context.is_safe_request_id`); anything else (empty, oversized, containing
CRLF or other control characters, whitespace) is discarded and a fresh ID is generated instead.
This is a log/header-injection defence: an attacker-controlled request ID is echoed back in a
response header and written to logs verbatim, so it must be constrained before either happens.

## Logs
Every JSON log line includes `request_id` (via a contextvar, since the formatter has no access
to the `Request` object) and `trace_id` (`null` until Phase 16). The middleware also writes one
access line per request; its fields are documented in `logging.md`.

The contextvar is deliberately not reset when the request ends: on an unhandled exception the
error handler runs after the middleware has unwound and still needs the ID for its own log
line. Under uvicorn each request runs in its own asyncio task, so the value cannot leak
between requests.

## Errors and the response header
The standard error contract's `request_id` field (see `docs/api/error-handling.md`) is always
populated from the same per-request context.

The `X-Request-ID` response header is set in two places, because there are two paths a
response can take:

- Normal and handled-error responses pass back through `RequestIDMiddleware`, which sets it.
- An **unhandled exception** produces its 500 in Starlette's `ServerErrorMiddleware`, which sits
  *outside* all user middleware, so that response never passes back through
  `RequestIDMiddleware`. `app/core/exceptions._error_response` therefore sets the header too.
  (Until Phase 14 this path returned no header; the earlier version of this document claimed
  every response carried it, which was wrong for 500s.)
