# Distributed tracing

OpenTelemetry traces follow one request through the API, the database, SQS and the worker.
Spans are created by hand at five places (`app/core/tracing.py` and the call sites below);
ADR-006 explains why not auto-instrumentation.

## What is traced

| Span | Kind | Created by | Name |
|---|---|---|---|
| HTTP request | SERVER | `RequestIDMiddleware` | `GET /api/v1/users/{user_id}` (method alone when no route matched) |
| Service operation | INTERNAL | `@traced` on every service method | `OrderService.create_order` |
| Database statement | CLIENT | `attach_database_tracing` | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `OTHER` |
| SQS publish | PRODUCER | `SQSEventPublisher` | `send <queue>` |
| EventBridge publish | PRODUCER | `EventBridgeEventPublisher` | `put_events <bus>` |
| Worker message | CONSUMER | `Worker._process` | `process OrderCreated` (`process unknown` for unrecognised types) |

A trace for `POST /api/v1/orders` therefore reads: server span -> `OrderService.create_order`
-> database statements and `send <queue>` -> (in the worker) `process OrderCreated`.

`/health/live`, `/health/ready` and `/metrics` are not traced: probes and scrapes arrive every
few seconds from every pod and would bury real traffic. They are still logged and counted.
Database statements outside any trace (the readiness `SELECT 1`, migrations) get no span, so
there are no parentless database roots.

Span names are low-cardinality on purpose: a route template, never a raw path; an unrecognised
HTTP method becomes `_OTHER`; an event type the worker does not handle becomes `unknown`.

## Crossing SQS
`SQSEventPublisher` injects the W3C `traceparent` (and `tracestate`) into the SQS **message
attributes**, inside the send span. The worker reads them back, so its `process` span is a child
of the `send` span and the whole flow is one trace. A message with no trace context (a foreign
producer, an old message) starts a new trace. Trace context is transport metadata, so it is not
part of the event envelope and the envelope schema is unchanged.

**EventBridge consumers do not join the trace.** `PutEvents` has no per-entry attribute for it
(only an X-Ray header in a different format), and the only other place is the event payload,
which would put transport metadata in the domain schema. The publish itself is still a span in
the caller's trace.

## Log correlation
Every log line carries `trace_id` (32 hex characters) and `span_id` (16). A line logged inside a
span gets that span's IDs, so a worker log line carries the trace ID of the request that caused
it. In CloudWatch Logs Insights:

```
fields @timestamp, level, logger, message
| filter trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
| sort @timestamp asc
```

IDs are generated even for requests that are not sampled, so logs stay correlatable whatever
the sampling ratio. One line needs special handling: Starlette logs an unhandled exception
*after* the request span has ended, so the middleware also keeps the IDs as a request-level
fallback; without it that line, the most important one, would have no trace ID.

## What a span never contains
- **Exception messages.** A span records the exception *type* (`error.type`) and sets status
  ERROR; the message and traceback are in the logs, redacted, under the same `trace_id`.
  Exception text can hold personal data or credentials.
- **SQL text.** Only the operation (`db.operation.name`) and database (`db.system.name`).
  SQLAlchemy's error text includes the bound parameters.
- **Query strings, headers, bodies.** `url.path` is the path only.
- **Baggage.** Only W3C trace context is propagated; baggage carries arbitrary key/values and
  would be accepted from untrusted callers.

Expected outcomes are not errors: an `AppException` below 500 (not found, conflict, validation)
leaves a span's status unset and only records `app.error.code`, and a 4xx server span is not an
error either, so error-trace views show real faults.

## Configuration
| Variable | Default | Meaning |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Collector **base** URL, e.g. `http://localhost:4318` (`/v1/traces` is appended). Unset: spans are created and appear in logs but are not exported. |
| `TRACING_SAMPLE_RATIO` | `1.0` | Fraction of *new* traces sampled (`ParentBased` + `TraceIdRatioBased`). |
| `TRACING_TRUST_INBOUND_CONTEXT` | `false` | Continue a trace from an inbound `traceparent`. |

The provider is process-wide and configured once; the first call wins. The API and the worker
are separate processes and appear as separate services (`<app name>` and `<app name>-worker`).

### Trusting inbound trace context
Off by default. With `ParentBased` sampling, a caller's sampled flag overrides our ratio, so an
untrusted client that sends `traceparent: ...-01` can force every one of its requests to be
sampled (cost amplification) and choose our trace IDs. Turn it on only behind a gateway you
control that sets or sanitises the header.

## Trying it locally (not tested here)
```
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
uv run uvicorn app.main:app --reload
```
then open http://localhost:16686.

## Limits and not done yet
- **EventBridge consumers do not join the trace** (above).
- **The server span ends when the handler returns the response object**, so time spent
  streaming the body is not included; the duration metrics have the same boundary.
- **Backend compatibility is unconfirmed.** The application emits standard W3C trace IDs over
  OTLP. Whether the chosen backend (for example X-Ray, which has its own trace-ID conventions)
  accepts them directly or needs the collector to translate is to be confirmed when the
  collector is provisioned (Phases 26 and 28).
- **Spans are exported in batches**, flushed when the process exits normally; a hard kill can
  lose the last few seconds. The worker's graceful shutdown (SIGTERM) exits normally.
- **No spans for Alembic migrations.**
- **Trace-based alarms and dashboards** are Phase 28.

## Testing
- `tests/unit/test_tracing.py`: settings, sampling (including why inbound context is not
  trusted), propagation round trip and malformed headers, and the `@traced` decorator (client
  errors are not span errors; exception messages never reach a span).
- `tests/unit/test_trace_logging.py`: trace and span IDs on log lines, and the fallback.
- `tests/unit/test_database_tracing.py`: statement spans against SQLite, including failure and
  no span outside a trace.
- `tests/unit/test_event_tracing.py`: publish spans and `traceparent` in the SQS attributes.
- `tests/unit/test_worker_tracing.py`: the worker continues the trace, and its logs carry the IDs.
- `tests/integration/test_request_tracing.py`: server spans, untraced paths, inbound-context
  trust, log correlation, and (with `TEST_DATABASE_URL`) service and database spans nested under
  a request through the real asyncpg driver.
