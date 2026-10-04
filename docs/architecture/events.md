# Event architecture

## Model

FastAPI (OrderService.create_order)
|
| OrderCreated
v
EventPublisher (protocol)
|
v
LoggingEventPublisher (Phase 11, current)
SQS adapter (Phase 12)
EventBridge adapter (Phase 13)


Business logic (`app/services/order_service.py`) depends only on the `EventPublisher`
protocol (`app/events/base.py`), never on an AWS SDK directly. Swapping the logging
implementation for a real broker touches `app/main.py` only.

## Envelope
| Field | Purpose |
|---|---|
| `event_id` | Lets a downstream consumer de-duplicate (idempotent processing). |
| `event_version` | Lets the payload shape evolve without breaking consumers. |
| `occurred_at` | When the fact became true in the domain, not when it was published. |
| `source` | Which service produced the event. |
| `data` | Event-specific payload. |

Immutable (`frozen=True`): an event is a record of something that already happened.

## Current events
`OrderCreated` - published when an order is successfully created, after the DB commit.

## Reliability (revisited in Phase 12)
Publishing is best-effort: the order is already durably committed before publish is
attempted, and a publish failure is logged but does not fail the request. Real retry/DLQ
handling arrives with the SQS adapter in Phase 12.

## Testing
- `tests/unit/test_events.py` - envelope shape, immutability, InMemoryEventPublisher.
- `tests/unit/test_order_service.py` - published on success, none on failure, failing
  publisher does not fail order creation.
- `tests/integration/test_order_events.py` - full HTTP-to-publish path.
