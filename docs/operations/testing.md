# Testing

## Layers
| Layer | Directory | Needs | What it checks |
|---|---|---|---|
| Unit | `tests/unit/` | nothing | Business rules, schemas, the formatter, publishers, the worker: with fakes, SQLite and moto. |
| Integration | `tests/integration/` | some need `TEST_DATABASE_URL` | The HTTP stack, repositories and migrations against a real PostgreSQL. |
| Contract | `tests/contract/` | the live-response tests need `TEST_DATABASE_URL` | The generated OpenAPI document, and that real responses conform to it. |
| End to end | `tests/e2e/` | `TEST_DATABASE_URL` | A few journeys across API, database, SQS and worker. |

The layers are markers too: `uv run pytest -m contract`, `-m e2e`, or `-m "not e2e"` for a fast
run. Tests that need a database are skipped, not failed, when `TEST_DATABASE_URL` is unset. The
database fixtures are in `tests/conftest.py` so every layer can use them. Setup for the database
is in `docs/deployment/docker.md` (the compose stack creates an `app_test` database).

## Contract tests
The contract is the OpenAPI document FastAPI generates (`app.openapi()`), and `CONTRACT` in
`tests/contract/openapi_helpers.py` is the API surface the project has promised: 13 operations,
each with its method, path, success status and documented error statuses.

**Static checks on the document** (`test_openapi_contract.py`):
- It is valid OpenAPI (`openapi-spec-validator`).
- The surface is exactly `CONTRACT`: nothing added, removed or renamed without changing it.
- Operation IDs are unique snake case; every operation has a summary and a tag.
- Each operation documents exactly its expected success status and error statuses.
- Every 4xx/5xx response declares the one error schema (`code`, `message`, `request_id`).
- Success responses have the documented shape; list responses are pages.
- Money is an integer (`exclusiveMinimum: 0`), order status is a closed set, currency is
  `^[A-Z]{3}$`, and request bodies reject unknown fields.
- Pagination is bounded (`limit` 1-100, default 20; `offset` >= 0).
- Every `/api/v1` operation declares bearer security; health endpoints are open.
- Each model's examples exist and validate against their own schema.

**Live responses against the document** (`test_runtime_contract.py`, `test_access_contract.py`):
each response must have a *documented* status, a body that validates against the documented
schema, an `X-Request-ID` header, and, for errors, a body `request_id` equal to that header.
Pagination is also checked for deterministic ordering and for pages that neither overlap nor skip.

A change to the API therefore fails a test until `CONTRACT` (and the docs) are updated on purpose.

## End-to-end journeys
Deliberately three (`tests/e2e/test_journeys.py`); the detail lives in the other layers.
1. **API -> SQS -> worker:** creating an order publishes an event, the worker consumes and
   acknowledges it, and one trace ID connects the request span, the worker span and the worker's
   log line.
2. **Order lifecycle and integrity:** a user with orders cannot be deleted; an order only moves
   forward; its amount freezes once processing; only pending or cancelled orders can be deleted.
3. **Failure isolation:** an unreachable queue does not fail order creation, and the failure is
   visible in the logs and as an error span.

## Not covered here
- **Load and performance** (Phase 31) and **resilience scenarios** such as database outage and
  worker crash (Phase 32).
- **Coverage measurement.** No coverage tool or threshold is configured.
- **Running against a deployed environment.** The e2e tests run the application in-process; a
  smoke test against a real deployment belongs with the pipeline (Phases 29-30).
