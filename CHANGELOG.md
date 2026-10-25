# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Repository bootstrap (Phase 1): directory layout, tooling configuration, project documents.
- FastAPI application skeleton (Phase 2): app factory, typed settings, JSON logging
  foundation, centralised error contract, `/health/live` and `/health/ready`.
- Configuration (Phase 3): database settings with pool tuning, `DATABASE_URL` held as  a  
  secret, required in staging/prod, validation errors that never echo input values.
- Database layer (Phase 4): async engine and session factory, `User` model, Alembic
  (async env, initial `users` migration), database-aware `/health/ready` (503 `NOT_READY` on failure),
  integration tests against an isolated `TEST_DATABASE_URL` database.
- User domain (Phase 5): full CRUD, case-insensitive unique email, pagination, deterministic
  ordering (created_at, id), `PATCH` semantics that require at least one non-null field.
- Order domain (Phase 6): full CRUD, integer minor-unit money (never float), ISO 4217
  currency validation, PENDING -> PROCESSING/CANCELLED -> COMPLETED/CANCELLED status machine, amount only editable while PENDING, deletion restricted to PENDING/CANCELLED, filtering by user_id/status.
- Error handling (Phase 7): AuthenticationException (401 + WWW-Authenticate) and
  AuthorizationException (403) added to the exception hierarchy ahead of Phases 9-10; full test coverage of the standard error shape across every error path.
- Request correlation (Phase 8): `RequestIDMiddleware` reads a safely-formatted inbound
  `X-Request-ID` or generates one, exposes it via request state and a contextvar, returns it on every response (success and error), and includes it (plus a placeholder `trace_id`) in every structured log line. Inbound IDs are validated against an allowlist and never trusted as a security identity.
- Authentication (Phase 9): Fix `get_current_principal` was reading settings via the globally
  cached `get_settings()` (environment-variable derived) instead of the app's own
  `Settings` instance, so an app built from an explicit `Settings` object (as tests do)
  could silently validate against the wrong OIDC configuration. Introduced
  `get_app_settings()`, reading `request.app.state.settings`; `create_app()` now stores
  the settings it was built with on `app.state`.
- Authorization (Phase 10): Implement authentication using a standard OIDC/OAuth2
  JWT-compatible approach.
- Event Architecture (Phase 11): Introduce an event abstraction. Create a domain event 
  model.
- SQS Integration (Phase 12): Implement an SQS adapter.
- EventBridge integration (Phase 13): `EventBridgeEventPublisher` (`app/events/eventbridge.py`),
  selected when `EVENTBRIDGE_BUS_NAME` is set. `MultiEventPublisher` composes SQS and
  EventBridge when both are configured, so `OrderService` always sees a single
  `EventPublisher` regardless of how many sinks are active, and one sink failing never
  stops the event reaching the others. ADR-004 documents the SQS-vs-EventBridge boundary
  (work queue vs. event routing). Tested via `moto` (an EventBridge rule routed to a
  target SQS queue, since EventBridge has no read-back API of its own).
- Structured logging (Phase 14): log field names now match the plan (`method`, `route`,
  `status_code`, `duration_ms`; previously `http_*`). `route` is the matched path template
  rather than the raw path, with the raw path in `path` (no query string). Any `extra={...}`
  field is now emitted (the formatter previously dropped everything outside a fixed allowlist,
  so the worker's `order_id`/`user_id` never appeared). Secrets are redacted as a backstop (by
  key name, and bearer tokens/JWTs/URL passwords in messages and tracebacks); `botocore`,
  `boto3` and `urllib3` are held at WARNING+; uvicorn's duplicate access log (which includes
  query strings) is silenced. Fix: a 500 from an unhandled exception now carries
  `X-Request-ID` and is access-logged; before, it had neither.
- Metrics (Phase 15): Prometheus metrics at `GET /metrics` - `http_requests_total`,
  `http_request_duration_seconds`, `http_errors_total` (5xx) and
  `database_operation_duration_seconds` (statement timing via SQLAlchemy engine events, failed statements included). One `Metrics` object and registry per app. Labels are bounded: `route` is the path template (`unmatched` for 404s), unrecognised HTTP methods collapse to `OTHER`, database `operation` is only the SQL verb. Recording is done in the existing request middleware from the same duration and route as the access log, and can never fail a request.
- Distributed tracing (Phase 16): OpenTelemetry (API, SDK, OTLP/HTTP exporter) with hand-written
  spans for the HTTP request, each service operation (`@traced`), each database statement,
  SQS/EventBridge publication and each worker message. W3C trace context crosses SQS in the
  message attributes, so one trace spans API -> database -> SQS -> worker. `trace_id` and
  `span_id` now appear on every log line, including the unhandled-exception line (a
  request-level fallback covers it, since Starlette logs it after the span ends). Inbound
  `traceparent` is ignored unless `TRACING_TRUST_INBOUND_CONTEXT` is set; spans never contain
  exception messages or SQL text; health and metrics requests are not traced. ADR-006 records
  the observability architecture. Not propagated: EventBridge consumers.
- Containerisation (Phase 17): multi-stage `Dockerfile` (dependencies installed with
  `uv sync --frozen --no-dev`; slim runtime image running as numeric non-root UID 10001 with a
  liveness `HEALTHCHECK`, exec-form `CMD`, one uvicorn process; no uv, build tools or credentials in
  the final image) and a `docker-compose.yml` development stack (PostgreSQL 16 with a test
  database, a one-off Alembic `migrate` service, the API, and an optional `worker` profile;
  loopback-only ports, read-only root filesystem, dropped capabilities). Static tests guard these
  properties. Known gap: no local identity provider, so `/api/v1/*` returns 503 under compose until
  OIDC settings are supplied.
- Automated testing (Phase 18): contract tests (`tests/contract/`) check the generated OpenAPI
  document (valid, an exact deliberate API surface, documented status codes, one error schema,
  integer money, bounded pagination, bearer security, self-validating examples) and that real
  responses conform to it (documented status, schema-valid body, `X-Request-ID`, deterministic
  pagination). Three end-to-end journeys (`tests/e2e/`): API -> SQS -> worker under one trace ID,
  the order lifecycle and referential integrity, and an unavailable queue not failing order
  creation. `pytest` markers `contract` and `e2e`. The database fixtures moved to
  `tests/conftest.py` so every layer can use them. Fix found by the contract tests:
  `/health/ready`'s 503 now documents the standard error schema.
- Quality tooling (Phase 19): `scripts/check.sh` is the single entry point for every gate, in CI's
  order (`uv lock --check`, `ruff format --check`, `ruff check`, `mypy`, `pytest --cov`), with
  `--no-tests` for a fast static pass. mypy now covers `worker/` as well as `app/` and takes its
  scope from configuration. Branch coverage of `app/` and `worker/` is measured (with
  `concurrency = greenlet` so SQLAlchemy's async code is counted), with a floor that only goes up.
  pytest runs with `--strict-markers --strict-config`. Local pre-commit hooks (ruff format and
  check, lock check; mypy on push) use the project's pinned tools. Guard tests keep the gates from
  being dropped or loosened by accident.
