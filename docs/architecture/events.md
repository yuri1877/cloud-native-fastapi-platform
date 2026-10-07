# Event architecture

## Model

FastAPI (OrderService.create_order)
|
| OrderCreated
v
EventPublisher (protocol)
|
+--------------------+
v v
SQSEventPublisher EventBridgeEventPublisher
(work queue, worker) (routing, other integrations)


Business logic (`app/services/order_service.py`) depends only on the `EventPublisher`
protocol (`app/events/base.py`), never on an AWS SDK directly. `app/main.py` decides, from
settings alone, which of `LoggingEventPublisher`, `SQSEventPublisher`,
`EventBridgeEventPublisher`, or a `MultiEventPublisher` wrapping both is active - the
service layer, and its tests, are unaffected either way. See ADR-004 for why both SQS and
EventBridge exist and what each is for.

## Envelope
| Field | Purpose |
|---|---|
| `event_id` | Lets a downstream consumer de-duplicate when the same event is delivered more than once. |
| `event_version` | Lets the payload shape evolve without breaking old consumers. |
| `occurred_at` | When the fact became true in the domain, not when it was published. |
| `source` | Which service produced the event - also used as EventBridge's `Source` field and for rule matching. |
| `data` | Event-specific payload. |

Immutable (`frozen=True`): an event is a record of something that already happened.

## Current events
`OrderCreated` - published when an order is successfully created, after the DB commit.

## SQS adapter and worker
`SQSEventPublisher` (`app/events/sqs.py`), selected when `SQS_QUEUE_URL` is set. `worker/`
long-polls the queue, dispatches by `event_type`, handles SIGTERM/SIGINT.

## EventBridge adapter
`EventBridgeEventPublisher` (`app/events/eventbridge.py`), selected when
`EVENTBRIDGE_BUS_NAME` is set. `put_events` doesn't raise on a per-entry failure -
`FailedEntryCount` is checked explicitly. Routing (rules, targets) is infrastructure
configuration (Terraform, Phase 26), not application code.

## Multiple sinks
When both are set, `app/main.py` wraps both in a `MultiEventPublisher`
(`app/events/publishers.py`): every publish attempts all sinks independently, so one
failing never stops the event reaching the others. Failures are collected and raised
together as a single `ExceptionGroup`.

## Reliability
Publishing is best-effort at the point of call: the order is already committed before
publish is attempted, and a publish failure is logged, not raised. Once a message reaches
SQS, delivery to the worker is reliable (deleted only after the handler succeeds; a failed
handler leaves it for redelivery, eventually routed to a DLQ via a redrive policy). SQS
idempotency is enforced via `event_id` against `ProcessedEventTracker`.

## Testing
- `tests/unit/test_events.py` - envelope, `InMemoryEventPublisher`, `MultiEventPublisher`.
- `tests/unit/test_order_service.py`, `tests/integration/test_order_events.py` - publish on
  success, none on failure, failing publisher doesn't fail order creation.
- `tests/unit/test_sqs_publisher.py`, `test_worker_consumer.py` - SQS adapter and worker.
- `tests/unit/test_eventbridge_publisher.py` - verified via a moto rule routing to a target
  SQS queue (EventBridge has no read-back API of its own); non-matching events aren't
  routed; a rejected entry raises.
- `tests/unit/test_event_publisher_wiring.py` - `_build_event_publisher` picks correctly
  across all four SQS/EventBridge configuration combinations.
