# Structured logging

Every log record is one JSON object written to stdout (`app/core/logging.py`). In AWS the
container runtime ships stdout to CloudWatch Logs; the application never writes log files.

```json
{
  "timestamp": "2026-10-08T10:15:30.123456+00:00",
  "level": "INFO",
  "service": "cloud-native-fastapi-platform",
  "environment": "prod",
  "logger": "app.access",
  "message": "request completed",
  "request_id": "9f1c...e2",
  "trace_id": null,
  "method": "GET",
  "route": "/api/v1/users/{user_id}",
  "path": "/api/v1/users/3f2b8c1e-5a4d-4c7e-9b1a-0d6e8f2a7c11",
  "status_code": 200,
  "duration_ms": 12.41
}
```

## Fields
Canonical fields on every line:

| Field | Source |
|---|---|
| `timestamp`, `level`, `logger`, `message` | the log record (ISO-8601, UTC) |
| `service`, `environment` | `APP_NAME`, `APP_ENV` |
| `request_id` | the request's correlation ID (contextvar); `null` outside a request |
| `trace_id` | `null` until distributed tracing arrives in Phase 16 |

Any `extra={...}` passed to a logging call is included as additional fields. Canonical fields
always win a name clash, so a caller cannot spoof `service` or `request_id`.

Fields emitted by the application today:

| Where | Fields |
|---|---|
| Access line (`app.access`, one per request) | `method`, `route`, `path`, `status_code`, `duration_ms` |
| Domain events (`app.events`) | `event_id`, `event_type`, `event_version` |
| Worker (`worker`, `worker.handlers`) | `queue_url`, `event_id`, `event_type`, `order_id`, `user_id` |
| Failures | `exception` (the redacted traceback) |

`route` is the matched path **template** (`/api/v1/users/{user_id}`), which is bounded and safe
to aggregate on; a request that matched no route is logged as `unmatched`. `path` is the raw path, kept for debugging, and never includes the query string. The template is built from the
real path by replacing each matched path-parameter value with its `{name}`, not read from the
matched route object (whose `path` can omit a router prefix). A parameter whose value equals a
literal segment would template that segment too, and a multi-segment `{name:path}` parameter
would not be templated; this API has neither case.

## Levels
The access line is `INFO`, or `ERROR` for a 5xx response. Expected client errors (401, 404,
422) are not warnings, so they do not raise the level.

## Secrets
The primary control is not logging secrets at all: headers, bodies and query strings are never logged. Redaction is a backstop for mistakes, in the formatter:

- Values under a key containing `password`, `secret`, `token`, `authorization`, `cookie`,
  `credential`, `api_key`, `private_key` or `database_url` are replaced with `[REDACTED]`
  (recursing into dicts and lists).
- In messages and tracebacks, bearer tokens, JWTs and the password in a `scheme://user:pw@host`
  URL are replaced.
- `botocore`, `boto3` and `urllib3` are held at `WARNING` or above regardless of `LOG_LEVEL`,
  because at `DEBUG` they log request headers (including AWS session tokens).
- uvicorn's own access log is silenced: it duplicates the access line and unlike          
  it, includes he query string, which can carry tokens.

Redaction is pattern-based and best effort. It will not catch a secret in an unrecognisable
format, so it does not replace reviewing what a new log line contains.

## Not done yet
- `trace_id` stays `null` until Phase 16.
- Events do not carry the originating `request_id`, so a worker log line cannot yetbe      
  joined to
  the API request that caused it. Propagating a correlation/trace ID through the event envelope
  belongs with the tracing work in Phase 16.
- Nothing is shipped or alarmed on yet; CloudWatch log groups and alarms are Phase 28.

## Testing
- `tests/unit/test_logging.py`: canonical fields, extras, name clashes, redaction (keys,   
  nested values, messages, arguments, tracebacks), and `configure_logging`.
- `tests/integration/test_request_logging.py`: the access line's fields, route template vs 
  raw path, `unmatched`, no query string or credentials in the output, and an unhandled exception being logged with its request ID.
