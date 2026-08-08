# Phase 5.9 — Commerce Event Reliability & Operational Hardening

## Status

Implemented. Approval depends on the complete validation matrix recorded in the
Phase 5.9 review report.

## Existing architecture audited

The repository has one PostgreSQL transactional outbox, introduced with Variant
normalization and reused by Cart, Checkout, Orders, Payments, Reservations,
Shipments, Returns/Refunds, Promotions, and Notifications. Those services flush
business state and identifier-only events through the same request-owned
transaction. Notifications consumes supported source events from PostgreSQL in a
Celery task and uses source-event/channel uniqueness for logical idempotency.

Inventory and Pricing previously emitted only through the in-process publisher.
They now use a transactional publisher backed by the same `event_outbox` and
retain the existing structured-log delegate. No event payload contract changed,
and no second outbox or broker was introduced.

## Failure model and lifecycle

```text
PENDING --claim--> PROCESSING --success--> PUBLISHED
   ^                    |
   |                    +--transient failure/backoff--+
   |                    +--retry exhausted-----------> FAILED
   +--admin recovery---- FAILED
   +--expired lease----- PROCESSING
```

`DISPATCHED` is reserved for an adapter-confirmed broker handoff. The Phase 5.8
notification consumer reads PostgreSQL directly, so its successful terminal state
remains `PUBLISHED`.

Each row records production time, next availability, claim owner and time,
attempt count, last error, last update, publication time, and optimistic version.
Consumer receipts have a unique event/consumer key and record durable completion.

## Claiming and crash recovery

Claims use PostgreSQL `FOR UPDATE SKIP LOCKED`; concurrent workers cannot claim the
same eligible row. A claim records `PROCESSING`, the worker identifier, timestamp,
and incremented attempt count. A process that dies before its transaction commits
leaves the source row pending because PostgreSQL rolls back the claim. A committed
claim whose worker later dies becomes eligible after the configured lease timeout.

## Retry and terminal failure

Unexpected processing failures use deterministic bounded exponential backoff:
`base_seconds * 2 ** (attempt - 1)`. Before exhaustion the row returns to
`PENDING` with a future `available_at`; at exhaustion it remains `FAILED` with a
sanitized diagnostic. Normal notification delivery retry behavior is unchanged.

## Idempotency and partial failure

Notifications retains its unique source-event/customer/channel constraint,
unique successful-delivery constraint, and stable gateway idempotency key. A
unique consumer receipt additionally makes durable consumption observable. The
database transaction marks an event processed only after notification state and
the receipt are flushed. A database failure rolls the unit of work back, leaving
the durable source event available for a later attempt.

## RabbitMQ behavior

PostgreSQL remains the source of truth. Commerce commits never depend on RabbitMQ.
If RabbitMQ cannot enqueue the scheduled Celery dispatch task, outbox rows remain
durable and unchanged. Celery publication retry and publisher confirmation are
enabled, late acknowledgement and worker-loss rejection are enforced, prefetch is
one, and Celery beat schedules dispatch every ten seconds. Processing resumes when
the broker and workers recover.

## Operational recovery

Administrators with `admin:access` can inspect terminal failures and expired
claims with `GET /api/v1/admin/events`. They can safely return one eligible event
to `PENDING` with `POST /api/v1/admin/events/{event_id}/recover`. The endpoint does
not expose payloads or arbitrary mutation and rejects healthy/in-flight/completed
events with `404`.

## Observability

Low-cardinality Prometheus counters cover creation, claims, processing failures,
successful processing, retries, recovery, and permanent failure. A histogram
measures processing duration. Worker identifiers and sanitized errors are stored
for operations but are not metric labels; payloads are not logged or returned by
the administration API.

## Production-backed verification

Focused tests cover atomic rollback, durable source events without a broker,
competing PostgreSQL claimers, lease expiry, deterministic backoff, retry
exhaustion, idempotent notification consumption and receipts, and authenticated
administrator recovery. Existing Phase 5 commerce and notification suites remain
the regression contract.

