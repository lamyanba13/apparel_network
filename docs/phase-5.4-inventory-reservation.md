# Phase 5.4 — Inventory Reservation

## Status

Approved on 2026-08-04 after the complete backend, frontend, migration, API,
static-analysis, and infrastructure validation matrix passed.

## Boundary

Inventory Reservation is a customer-owned, Store-scoped bounded context that
temporarily holds the Inventory referenced by a captured Payment's Order. It owns
Reservation lifecycle, immutable Reservation Items, expiration, capacity
accounting, optimistic versions, transactional events, and metrics.

A Reservation is not Inventory. It does not alter on-hand, reserved, or available
Inventory quantities. It does not process Payments, create shipments, issue
invoices, or perform fulfillment.

## Creation and ownership

Creation validates the Payment, Order, and Checkout through their production
application services. The Payment must be `CAPTURED`, the Order must be
`CONFIRMED`, and the Checkout must be `CONFIRMED`. Their Order, customer, and Store
identifiers must match.

Each Reservation Item is copied from an immutable Order Item and records Inventory
Item, Variant, quantity, and validated Inventory version. Exactly one unexpired
active Reservation may exist for an Order.

## Inventory interaction

Reservation validation locks each referenced Inventory row for the duration of the
request, verifies Store and Variant ownership, requires active Inventory, requires
the current version to match the Order snapshot, and checks available quantity.

Capacity calculation subtracts quantities held by all unexpired active Reservation
Items from Inventory's current available quantity. This prevents concurrent holds
from oversubscribing stock without writing Inventory quantity columns. Locks are
acquired in stable Inventory-ID order to avoid deadlocks.

## Lifecycle

Creation atomically materializes:

```text
CREATED -> ACTIVE
```

An active Reservation may transition to exactly one terminal status:

```text
ACTIVE -> CONSUMED
ACTIVE -> RELEASED
ACTIVE -> EXPIRED
```

There is no reopening. Consumed Reservations remain available as durable future
Fulfillment input. Released and expired Reservations are soft-deleted while their
Items and outbox history are retained. Stale transitions return `409 Conflict`.

## Expiration

The default lifetime is 30 minutes. Expiration is lazy: every list, detail, status,
release, or consume operation checks the current UTC timestamp. Reading or mutating
an overdue active Reservation atomically materializes `EXPIRED`, writes its outbox
event, records the duration metric, and releases its capacity. No scheduler or
background worker is introduced.

Capacity queries ignore an overdue active row immediately, even before its lifecycle
event is materialized. Creating a replacement for an overdue Order first
materializes the old expiration so the active-Order uniqueness constraint remains
correct.

## Persistence

`inventory_reservations` stores Order, Payment, customer, Store, lifecycle,
expiration, terminal timestamps, optimistic version, audit fields, and soft-delete
metadata. A partial unique index enforces one active Reservation per Order.

`inventory_reservation_items` stores immutable Inventory and Variant references,
quantity, Inventory version, and creation time. Repositories flush only; the
FastAPI database dependency owns commit and rollback with the outbox records.

## HTTP API

- `POST /api/v1/reservations`
- `GET /api/v1/reservations`
- `GET /api/v1/reservations/{reservation_id}`
- `POST /api/v1/reservations/{reservation_id}/release`
- `POST /api/v1/reservations/{reservation_id}/consume`
- `GET /api/v1/reservations/{reservation_id}/status`

Routes use `reservation:create`, `reservation:view`, `reservation:update`,
`reservation:consume`, and `reservation:release`. All reads and writes are scoped
to the authenticated customer; cross-user access returns `404`.

## Events and metrics

`reservation.created`, `reservation.activated`, `reservation.released`,
`reservation.expired`, and `reservation.consumed` use identifier-only
transactional outbox payloads. Lifecycle counters and an unlabeled duration
histogram provide low-cardinality observability.

## Future Fulfillment interaction

Phase 5.5 may consume an active Reservation through the approved application
service and then adjust Inventory through `InventoryService` in its own reviewed
workflow. Phase 5.4 consumption itself intentionally changes no Inventory quantity
and creates no shipment or invoice.

## Verification

The production-backed HTTP integration test traverses authentication,
authorization, Store, Catalog, Product, Variant, Inventory, Pricing, Cart,
Checkout, Order, Payment, Reservation, PostgreSQL, and the transactional outbox.
It uses no mocks, fake repositories, monkeypatches, or direct model insertion.
