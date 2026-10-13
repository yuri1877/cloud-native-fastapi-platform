# ADR-006: Observability architecture

## Context
The spec requires logs, metrics and traces, and a way to follow one request across the API, the
database, SQS and the worker. The target is AWS (EKS, CloudWatch), but the application should
not be written against one vendor's API.

## Decision
Three signals, each using the standard format for its kind:

- **Logs:** JSON on stdout, one object per line, shipped by the platform to CloudWatch Logs.
  Every line carries `request_id`, `trace_id` and `span_id`. Secrets are redacted as a backstop.
- **Metrics:** Prometheus text exposition at `GET /metrics` (Phase 15), with bounded labels.
- **Traces:** the OpenTelemetry API and SDK, exported over OTLP/HTTP to a collector, which
  forwards to whichever backend is chosen. The application only knows OTLP.

Tracing specifics:
- Spans are written by hand at five places: the HTTP request, a service operation, a database
  statement, an event publication and a worker message.
- W3C trace context crosses SQS in the message attributes. It is not added to the event envelope.
- An inbound `traceparent` is ignored unless explicitly trusted.
- A span records an exception's type, never its message, and never SQL text.
- `trace_id` is the join key between all three signals.

## Alternatives considered
- **Auto-instrumentation packages (FastAPI, SQLAlchemy, botocore).** Broader coverage of the
  semantic conventions for free, and less code to own. Rejected here because: the contrib
  packages are versioned separately (the 0.x beta line) and must track the SDK; where the FastAPI
  instrumentation sits relative to our own request middleware decides whether log lines inside a
  request carry the trace ID; the unhandled-exception path runs outside user middleware; the
  botocore instrumentation would create a span for every 20-second long-poll the worker makes;
  and we only need five touchpoints, where writing them ourselves lets us control exactly what
  attributes are recorded. The cost is that we maintain the instrumentation, and a library we do
  not wrap gets no spans.
- **The AWS X-Ray SDK directly.** Puts a vendor API in application code. OpenTelemetry plus a
  collector keeps the backend swappable.
- **Trace context in the event envelope.** Rejected: it puts transport metadata in the domain
  schema and makes every consumer depend on it. Message attributes are where messaging
  conventions put it.
- **Trusting inbound `traceparent` by default.** Rejected: with parent-based sampling a caller
  could force sampling of all its requests and choose our trace IDs.
- **CloudWatch Embedded Metric Format instead of Prometheus.** Viable on AWS, but couples the
  application to CloudWatch's format. It remains an option for worker metrics.

## Rationale
One `trace_id` on every log line and every span means any signal leads to the others. Standard
formats (JSON logs, Prometheus, OTLP) keep the application independent of the backend. Keeping
exception text and SQL out of spans keeps personal data and credentials out of a system that
usually has wider read access than the logs do.

## Consequences
- **Positive:** a single trace covers API, database, SQS and worker, and its ID finds the logs.
  The backend can change without touching application code. Sampling cost is controlled by
  configuration, and unsampled requests still have correlatable logs.
- **Negative:** instrumentation is hand-maintained. EventBridge consumers cannot join a trace.
  The tracer provider is process-wide and configured once, so tests share one provider and the
  first configuration wins. Spans carry no SQL text, so diagnosing a slow query relies on the
  database's own tooling. The server span ends when the handler returns the response object,
  excluding body-streaming time.
- **Deferred:** backend choice and collector deployment (Phases 26 and 28); X-Ray's trace-ID
  constraints are to be confirmed then.

## Status
Accepted
