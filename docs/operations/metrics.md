# Metrics

Prometheus-format metrics, served at `GET /metrics` (`app/api/metrics.py`). The metrics and
their registry live in `app/core/metrics.py`: one `Metrics` object per application, each with
its own `CollectorRegistry`.

## The metrics

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | counter | `method`, `route`, `status_code` | Requests handled. The status distribution is the `status_code` label. |
| `http_request_duration_seconds` | histogram | `method`, `route` | Request latency, measured in the request middleware. |
| `http_errors_total` | counter | `method`, `route` | Responses with a 5xx status. 4xx are client errors and are not counted. |
| `database_operation_duration_seconds` | histogram | `operation` | Time per SQL statement. `operation` is `SELECT`, `INSERT`, `UPDATE`, `DELETE` or `OTHER`. |

The implementation plan names the two histograms `http_request_duration` and
`database_operation_duration`. They carry a `_seconds` suffix here because Prometheus
convention is to put the base unit in the name, and the plan asks for Prometheus-compatible
naming where practical.

## Label cardinality
Every distinct label combination is its own time series, so every label value must come from a
small, bounded set:

- **`route`** is the matched path *template* (`/api/v1/users/{user_id}`), the same value the
  access log carries (see `logging.md`). A request that matched no route is `unmatched`, so a
  scanner probing random paths creates one series, not thousands.
- **`method`** is one of `GET HEAD POST PUT PATCH DELETE OPTIONS`; any other method a client
  sends is recorded as `OTHER`.
- **`status_code`** is a response code the application itself produced.
- **`operation`** is only the leading SQL verb. Table names and SQL text are never labels.

User IDs, order IDs, emails, request IDs and raw paths must never become label values.

## Histogram buckets
HTTP latency: 5 ms to 10 s. Database statements: 1 ms to 5 s. The boundaries set the resolution
of every percentile derived from them, so they should be revisited against the Phase 31 load
test results rather than treated as final.

## Example queries
```promql
# p95 latency per route over 5 minutes
histogram_quantile(0.95, sum by (le, route) (rate(http_request_duration_seconds_bucket[5m])))

# 5xx ratio, overall
sum(rate(http_errors_total[5m])) / sum(rate(http_requests_total[5m]))

# slowest database operation kind (p99)
histogram_quantile(0.99, sum by (le, operation) (rate(database_operation_duration_seconds_bucket[5m])))
```

## How database timing works
`attach_database_metrics` listens to SQLAlchemy's `before_cursor_execute` and
`after_cursor_execute` events on the engine underneath the `AsyncEngine`. A statement that
fails never reaches `after_cursor_execute`, so `handle_error` records it instead; a failing
or hanging database is exactly when these timings matter, and without that hook the start-time
stack on the connection would grow by one entry per failure. Statements that open with a
comment or a `WITH` clause are recorded as `OTHER`. Alembic migrations use their own engine and
are not measured. `/health/ready` runs `SELECT 1`, so readiness probes appear in the `SELECT`
count.

## Operating it
- **Run one worker process per container.** `prometheus_client` keeps its registry in process
  memory. With several uvicorn workers in one container, each scrape would reach an arbitrary
  one and the numbers would be wrong. Scale by adding pods, not workers (relevant to the Phase 17
  Dockerfile and Phase 24 EKS deployment).
- **`/metrics` is unauthenticated.** Scrapers do not carry user tokens. It must be reachable
  only from inside the cluster; the public ingress (Phase 25) must not route it.
- **The scrape itself is counted**, in the following scrape, as are health probes. Filter by
  `route` when building dashboards.
- Metrics are not in the OpenAPI schema.

## Not done yet
- **Worker metrics.** The worker is a separate process with no HTTP server, so it exports
  nothing. Worker failures and processing latency need either a small exposition endpoint in
  `worker/` or CloudWatch embedded metrics.
- **Queue depth and DLQ size.** SQS publishes these to CloudWatch itself; they are alarmed on
  in Phase 28, not re-exported from the application.
- **Process and runtime metrics** (CPU, memory, GC). Container-level CPU and memory come from
  the platform (Phase 28). `prometheus_client`'s `ProcessCollector` and `GCCollector` could be
  registered in `Metrics.__init__` if in-process figures are wanted.
- **Alerting rules and dashboards** (Phase 28).

## Testing
- `tests/unit/test_metrics.py`: counting, timing, 5xx vs 4xx, bounded method label,
  independent registries, the text format, and the statement classifier.
- `tests/unit/test_database_metrics.py`: the timing hooks against in-memory SQLite, including
  that a failed statement is recorded and leaves no stale state.
- `tests/integration/test_metrics_endpoint.py`: the endpoint and what a scrape contains after
  real requests (templates, `unmatched`, unrecognised methods, unhandled exceptions), that a
  broken metrics backend cannot fail a request, and, with `TEST_DATABASE_URL`, that statements
  through the real asyncpg driver are timed.
