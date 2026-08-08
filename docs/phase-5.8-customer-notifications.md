# Phase 5.8 — Customer Notifications & Commerce Events

## Status

Implemented and approved on 2026-08-08 after the complete production-backed
validation matrix passed.

## Boundary

Notifications is a customer-owned bounded context. It consumes identifier-only
commerce events from the existing transactional outbox, renders plain-text
templates, applies customer channel preferences, and records every delivery or
failure. It does not own Order, Payment, Shipment, Return, Refund, Promotion, or
Coupon state and never calls an external provider in the foundation phase.

## Delivery lifecycle

```text
PENDING -> QUEUED -> SENDING -> DELIVERED
                         |-> RETRYING -> QUEUED
                         |-> FAILED
PENDING --------------------> CANCELLED
```

`DELIVERED`, `FAILED`, and `CANCELLED` are terminal. Failed gateway attempts use
bounded exponential backoff. The source outbox record remains pending while any
enabled channel is awaiting retry and is published only after every channel is
terminal. The unique source-event, customer, and channel key prevents duplicate
notifications; a delivery has at most one success record.

## Channels and gateway

Email, SMS, push, and in-app channels share one provider-neutral protocol. The
Null gateway returns deterministic references, performs no network I/O, and is
the only configured Phase 5.8 adapter. Production templates are seeded for Order,
Payment, Shipment, Return, Refund, Promotion, and Coupon commerce events.

## Preferences

Preferences are owned by the authenticated customer and cover channel flags,
language, and marketing opt-in. Email and in-app are enabled by default. Commerce
events are transactional, so marketing opt-out never suppresses them; channel
flags still apply. Disabled-channel records transition to `CANCELLED` and are
soft deleted for auditability.

## HTTP API

- `GET /api/v1/notifications`
- `GET /api/v1/notifications/{notification_id}`
- `PATCH /api/v1/notifications/{notification_id}/read`
- `GET /api/v1/notifications/preferences`
- `PATCH /api/v1/notifications/preferences`
- `POST /api/v1/notifications/test`

Customer ownership is concealed with `404`. Read and preference mutations use
optimistic versions and return `409 Conflict` for stale requests. The test route
is restricted to administrators and uses the Null gateway.

## Events, worker, and observability

The notification worker selects supported pending outbox records with row locks,
dispatches enabled channels, and commits the notification, attempt, delivery, and
outbox state in one worker transaction. Notification-created, sent, failed, and
read events contain identifiers, versions, and timestamps only.

Low-cardinality metrics count notifications created, sent, failed, and retried by
channel. A channel-labelled histogram measures gateway latency. The dedicated
`notification-events` Celery queue has a dead-letter queue.

## Verification

The integration suite uses PostgreSQL, the production repositories, production
application services, the shared outbox, the real FastAPI application, production
authorization, and the deterministic Null gateway. It covers rendering, every
gateway method, dispatch idempotency, delivery and cancellation, preferences,
read state, stale versions, retries, persistence, metrics, permissions, and
cross-customer isolation without mocks or direct ORM inserts.
