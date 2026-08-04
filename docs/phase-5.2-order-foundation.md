# Phase 5.2 — Order Foundation

## Status

Implemented on 2026-08-04. Approval remains subject to the complete validation
matrix recorded with the phase handoff.

## Boundary

Order is the customer-owned, Store-scoped immutable commercial contract created
from a confirmed Checkout Session. It owns Order identity and lifecycle, immutable
Order Items, copied commercial snapshots, summaries, audit attribution, events,
and metrics.

Order does not process Payments, reserve or deduct Inventory, calculate tax or
shipping, issue invoices, or perform fulfillment.

## Checkout to Order transition

`OrderService.create` loads the customer-owned Checkout through the production
Checkout service and accepts only `confirmed` Sessions. PostgreSQL permits exactly
one Order for a Checkout Session. The service copies Checkout Item snapshots; it
never reads mutable Cart Items and never re-resolves Pricing or Inventory.

The request transaction flushes the Order, Items, and `order.created` outbox record
atomically.

## Immutable snapshots

Each Order Item freezes Product and Variant identifiers, quantity, Price ID, unit
price, currency, Inventory ID and version, and the later source snapshot timestamp.
No Item update or delete operation exists. Later changes to Cart, Pricing, or
Inventory do not alter an Order.

## Lifecycle

The only transitions are `PENDING -> CONFIRMED -> CANCELLED`. Confirmation records
`confirmed_at`. Cancellation is permitted only from `CONFIRMED`, records
`cancelled_at`, and soft-deletes the Order while retaining its Items. There is no
reopening. Stale writes return `409 Conflict`; cross-customer access returns `404`.

## Order numbering

Numbers use `ORD-YYYYMMDD-000001`. A dedicated non-cycling PostgreSQL sequence
allocates the six-digit suffix safely across concurrent processes. Allocation is
global, unique, monotonic, and gap-tolerant; rolled-back transactions may consume a
number. The date is the UTC allocation date. The format has a hard capacity of
999,999 allocations and must be superseded by a reviewed format before exhaustion.

## Persistence

`orders` stores ownership, source identifiers, number, lifecycle, frozen total,
audit fields, optimistic version, and soft-deletion metadata. `order_items` stores
the immutable per-Variant snapshots. PostgreSQL constraints enforce the boundary.
Repositories flush only; the FastAPI database dependency owns commit and rollback.

## HTTP API

- `POST /api/v1/orders`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `POST /api/v1/orders/{order_id}/confirm`
- `DELETE /api/v1/orders/{order_id}`
- `GET /api/v1/orders/{order_id}/summary`

Routes require `order:create`, `order:view`, `order:update`, or `order:confirm`.
Every query is scoped to the authenticated customer.

## Events and metrics

`order.created`, `order.confirmed`, and `order.cancelled` are identifier-only events
written through the transactional outbox. Low-cardinality Prometheus counters track
each successful transition.

## Future Payment boundary

A later Payment capability may reference a confirmed Order as stable input. It must
define attempts, idempotency, authorization/capture, refunds, and failure recovery
separately. Order never implies payment, stock reservation, tax, shipping,
fulfillment, invoicing, or settlement.

## Verification

The production-backed HTTP test traverses authentication, authorization, the full
business composition, PostgreSQL, and the outbox. It covers Checkout validation,
immutable snapshots, numbering, ownership, optimistic locking, lifecycle, soft
deletion, persistence, events, metrics, summaries, and OpenAPI without mocks.
