# Event architecture

## Model

FastAPI (OrderService.create_order)
|
| OrderCreated
v
EventPublisher (protocol)
|
v
LoggingEventPublisher (used when SQS_QUEUE_URL is unset)
SQSEventPublisher (Phase 12, current default once SQS_QUEUE_URL is set)
EventBridge adapter (Phase 13)


Business logic (`app/services/order_service.py`) depends only on the `EventPublisher`
protocol (`app/events/base.py`), never on an AWS SDK directly. Swapping which implementation
is active touches `app/main.py` only -- the service layer, and its tests, are unaffected.

## Envelope
| Field | Purpose |
|---|---|
| `event_id` | Lets a downstream consumer de-duplicate when the same event is delivered more than once (SQS gives at-least-once delivery, never exactly-once). |
| `event_version` | Lets the payload shape evolve without breaking old consumers. |
| `occurred_at` | When the fact became true in the domain, not when it was published. |
| `source` | Which service produced the event. |
| `data` | Event-specific payload. |

Immutable (`frozen=True`): an event is a record of something that already happened.

## Current events
`OrderCreated` - published when an order is successfully created, after the DB commit.

## SQS adapter and worker
`SQSEventPublisher` (`app/events/sqs.py`) implements `EventPublisher` against a standard
(non-FIFO) SQS queue; `app/main.py` selects it automatically when `SQS_QUEUE_URL` is set,
falling back to `LoggingEventPublisher` otherwise. SQS configuration is optional in every
environment, so the service is deployable before queue infrastructure exists.

`worker/` is a separate process (`python -m worker.main`) that long-polls the queue,
dispatches by `event_type` (`worker/handlers.py`), and handles SIGTERM/SIGINT for graceful
shutdown -- in-flight work finishes before the poll loop exits.

## Reliability
Publishing is best-effort at the point of call: the order is already committed before publish
is attempted, and a publish failure is logged, not raised. An outbox pattern would close this
gap and is a reasonable future enhancement.

Once a message reaches SQS, delivery to the worker is reliable: a message is only deleted
after its handler succeeds; a failed handler leaves it for redelivery, eventually routed to a
DLQ via a redrive policy (provisioned in Phase 26). Idempotency is enforced via `event_id`
against `ProcessedEventTracker`; the default in-memory tracker loses its record on restart,
noted as a known limitation in `worker/idempotency.py`.

## Testing
- `tests/unit/test_events.py`, `test_order_service.py`, `test_order_events.py` (integration) -
  from Phase 11.
- `tests/unit/test_sqs_publisher.py` - `SQSEventPublisher` against a `moto`-mocked queue.
- `tests/unit/test_worker_consumer.py` - dispatch, deletion, unknown-event handling, a failing
  handler leaving the message, and idempotent skip on redelivery.
