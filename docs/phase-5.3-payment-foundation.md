# Phase 5.3 — Payment Foundation

## Status

Approved on 2026-08-04 after the complete backend, frontend, migration, API,
static-analysis, and infrastructure validation matrix passed.

## Boundary

Payment is a customer-owned, Store-scoped bounded context that creates and tracks
Payment Intents for pending Orders. It owns provider abstraction, immutable amount
and ownership snapshots, lifecycle state, provider transaction history,
idempotency, optimistic versions, transactional events, and metrics.

Payment does not reserve or deduct Inventory, ship products, issue invoices,
perform refunds or settlements, or know Checkout behavior. It never writes Order
tables directly.

## Payment snapshot

Intent creation loads an owned Order through the production Order service and
accepts only `PENDING`. The Intent copies the Order ID, customer ID, Store ID,
currency, and subtotal. Later Order changes do not alter this Payment snapshot.
The initial Intent expires after 15 minutes; provider-specific expiration handling
is deferred until a real provider is approved.

## Lifecycle

The allowed transitions are:

```text
CREATED -> AUTHORIZED -> CAPTURED
   |            |
   +----------> FAILED
   |            |
   +----------> CANCELLED
```

`CAPTURED`, `FAILED`, and `CANCELLED` are terminal. There is no reopening.
Cancellation soft-deletes the Intent while retaining its append-only transaction
history. Stale writes return `409 Conflict`; cross-customer access returns `404`.

## Gateway abstraction

The application depends on the `PaymentGateway` protocol with `create_intent`,
`authorize`, `capture`, `cancel`, and `status` operations. Phase 5.3 supplies only
the deterministic `NullPaymentGateway`. It performs no network request and returns
stable provider references and minimal, non-sensitive payloads.

Provider payloads are retained privately in `payment_transactions` for future
reconciliation and are not returned by the customer API.

## Idempotency

`POST /api/v1/payments` requires the existing validated `Idempotency-Key` header.
The `(customer_id, idempotency_key)` pair is unique in PostgreSQL. Repeating a key
for the same Order returns the original Intent without invoking the gateway or
emitting another event. Reusing it for another Order returns `409 Conflict`.

Transition requests validate their optimistic version before invoking the gateway.
Future network gateways must additionally provide provider-side idempotency and
reconciliation because an external side effect cannot be enclosed by the local
PostgreSQL transaction.

## Order interaction

Only a pending Order may create a Payment. A successful capture asks the existing
Order service to perform its approved `PENDING -> CONFIRMED` transition in the same
request transaction. Payment never updates Order persistence directly. Failed or
cancelled Payments leave the Order pending.

## Persistence

`payment_intents` stores the Order and ownership snapshot, provider reference,
lifecycle timestamps, amount, currency, idempotency key, expiration, optimistic
version, audit fields, and soft-deletion metadata. `payment_transactions` is an
append-only provider interaction history containing provider transaction ID, event
type, status, amount, currency, private payload, and occurrence time.

Repositories flush only. The FastAPI database dependency commits or rolls back the
Intent, transaction history, Payment outbox event, and approved Order transition.

## HTTP API

- `POST /api/v1/payments`
- `GET /api/v1/payments`
- `GET /api/v1/payments/{payment_id}`
- `POST /api/v1/payments/{payment_id}/authorize`
- `POST /api/v1/payments/{payment_id}/capture`
- `POST /api/v1/payments/{payment_id}/cancel`
- `GET /api/v1/payments/{payment_id}/status`

Routes require `payment:create`, `payment:view`, `payment:update`,
`payment:capture`, or `payment:cancel`. Every operation is customer-scoped.

## Events and metrics

`payment.created`, `payment.authorized`, `payment.captured`, `payment.failed`, and
`payment.cancelled` use identifier-only transactional outbox payloads. Five
low-cardinality lifecycle counters and one unlabeled gateway-duration histogram
cover Payment processing.

## Future provider integrations

Razorpay, Stripe, and Cashfree adapters remain future work. Their approval requires
secret management, signed webhook verification, provider-side idempotency,
reconciliation, retry policy, failure classification, and private-payload review.
Refunds, settlements, invoices, and fulfillment remain separate capabilities.

## Verification

The production-backed HTTP integration test traverses authentication,
authorization, Store, Catalog, Product, Variant, Inventory, Pricing, Cart,
Checkout, Order, Payment, PostgreSQL, and the transactional outbox. It uses the
production Null gateway and no mocks, fake repositories, or direct model insertion.
