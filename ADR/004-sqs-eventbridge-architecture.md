# ADR-004: SQS and EventBridge architecture

## Context
The platform needs asynchronous processing (a durable work queue for the worker) and a way
for domain events to reach other consumers/integrations without the order service knowing
about them in advance. One service, AWS SQS, naturally fits the first need; a second,
EventBridge, fits the second. The spec requires both, and requires the distinction between
them to be documented rather than assumed.

## Decision
Use both, for different purposes, published independently from the same `OrderService` call:

SQS -> work distribution / buffering (the worker's durable queue, Phase 12)
EventBridge -> event routing / integration (other consumers/rules, Phase 13)


`OrderService` still depends on a single `EventPublisher` (`app/events/base.py`). When both
`SQS_QUEUE_URL` and `EVENTBRIDGE_BUS_NAME` are configured, `app/main.py` wraps both adapters
in a `MultiEventPublisher`, which publishes to each independently - so the service layer
never needs to know how many sinks exist, or that EventBridge exists at all.

## Alternatives considered
- **Publish only to EventBridge, with a rule routing a copy to SQS.** Rejected for this
  project: it moves the SQS/EventBridge relationship into Terraform-managed infrastructure
  (a rule + target), which is reasonable in a mature AWS deployment but obscures the
  distinction this ADR exists to document, and makes local/test behaviour depend on
  infrastructure rather than on `app/main.py` alone.
- **Replace SQS with EventBridge entirely** (EventBridge can target a Lambda or an HTTP
  endpoint directly). Rejected: EventBridge is a routing/fan-out service, not a queue - it
  doesn't provide the worker's pull-based processing model, visibility timeouts, or the
  simple redelivery semantics SQS gives the worker (`worker/consumer.py`).
- **A single generic "bus" abstraction hiding both services behind one interface with
  routing metadata.** Rejected as unnecessary complexity for this project's scope -
  `MultiEventPublisher` already gives `OrderService` a single call site; a routing layer
  would only be justified by a far larger number of event types and destinations.

## Rationale
- SQS's pull model, visibility timeouts and redrive-to-DLQ behaviour are what the worker
  needs for reliable, ordered-enough processing of a single well-known consumer's workload.
- EventBridge's rule-based routing is what other consumers (future services, analytics,
  external integrations) need, without the order service having to know who they are.
- Keeping both as implementations of the same `EventPublisher` protocol, composed via
  `MultiEventPublisher`, means adding or removing either sink is purely a wiring change in
  `app/main.py` - see `docs/architecture/events.md`.

## Consequences
- **Positive:** `OrderService` and its tests are completely unaffected by this decision -
  confirmed by Phase 11/12's tests still passing unchanged once EventBridge was added.
  Each sink fails independently (`MultiEventPublisher` attempts every publisher even if one
  raises), so an EventBridge outage cannot silently stop orders reaching the worker's queue.
- **Negative:** an event is published to each configured sink via a separate API call, not
  atomically - a reader of SQS and a reader of EventBridge are not guaranteed to see the
  event at exactly the same time, and if one sink fails the two drift further out of sync
  until the failed one is manually fixed.
- **Deferred:** which event types go to EventBridge versus SQS-only is decided per event
  (currently both get `OrderCreated`); this ADR covers the mechanism, not every future
  event's routing choice.

## Status
Accepted
