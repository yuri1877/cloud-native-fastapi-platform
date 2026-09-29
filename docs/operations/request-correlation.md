# Request correlation

## Flow
```
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
Returned in the X-Request-ID response header (success and error responses alike)
```

Implemented by `RequestIDMiddleware` in `app/core/middleware.py`, registered first in `create_app()`
so every response — including ones from later middleware or exception handlers — carries the header.

## Trust model
An inbound `X-Request-ID` is **never treated as a security identity** — it is not used for
authentication, authorization, or audit attribution, only for correlating log lines and
responses belonging to the same request. It must match `^[A-Za-z0-9_-]{8,128}$`
(`app/core/request_context.is_safe_request_id`); anything else (empty, oversized, containing
CRLF or other control characters, whitespace) is discarded and a fresh ID is generated instead.
This is a log/header-injection defence: an attacker-controlled request ID is echoed back in a
response header and written to logs verbatim, so it must be constrained before either happens.

## Logs
Every JSON log line includes `request_id` (via a contextvar, since the formatter has no access
to the `Request` object) and `trace_id` (`null` until Phase 16 adds distributed tracing). The
middleware itself logs one line per request with `http_method`, `http_route`, `http_status` and
`duration_ms`.

## Errors
The standard error contract's `request_id` field (see `docs/api/error-handling.md`) is now
always populated, taken from the same per-request context.
