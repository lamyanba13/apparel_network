# Phase 5.6 — Returns & Refund Foundation

## Status

Implemented and approved on 2026-08-05 after the complete validation matrix
passed.

## Boundary

Returns and Refunds form a customer-owned, Store-scoped bounded context for
post-delivery claims and provider-neutral reimbursement. It owns Return Items,
inspection dispositions, Return lifecycle, Refund lifecycle, provider transaction
history, optimistic versions, transactional events, and metrics.

It never changes Orders, Shipments, Payments, Reservations, Pricing, or Inventory
tables directly. It performs no automatic restocking and installs no external
refund provider.

## Eligibility and ownership

Only the purchasing customer may request a Return. Creation validates the owned
Order, Shipment, Payment, Order Items, and Inventory through their production
application services. The Order must remain confirmed, the Shipment must be
delivered, and the Payment must be captured. Every customer, Store, Order,
Shipment, and Payment identifier must match.

Requested quantities must be positive, belong to active immutable Order Items,
and remain within the quantity purchased after all non-rejected and non-cancelled
Returns are counted. Cross-user access returns `404`.

## Return lifecycle

```text
REQUESTED -> APPROVED -> RECEIVED -> INSPECTED
          -> REFUND_PENDING -> REFUNDED

REQUESTED -> REJECTED
APPROVED  -> CANCELLED
```

`REFUNDED`, `REJECTED`, and `CANCELLED` are terminal and cannot reopen. Rejected
and cancelled Returns are soft-deleted while Items and outbox history remain.
Every mutation requires the current optimistic version; stale requests return
`409 Conflict`.

Inspection requires a disposition for every Return Item. The service records
`RESTOCK`, `DAMAGED`, `INSPECTION_REQUIRED`, or `DISPOSE`, then moves atomically
through `INSPECTED` to `REFUND_PENDING`.

## Refund lifecycle

```text
PENDING -> PROCESSING -> COMPLETED
                    \-> FAILED
```

Only one Refund may exist per Return, which is stronger than the required single
successful Refund guarantee. Refund creation derives its amount and currency from
immutable Return Item snapshots. It requires an inspected Return awaiting refund,
a captured Payment, matching ownership, and sufficient remaining captured amount.

Completing a Refund advances the Return to `REFUNDED` in the same database
transaction. No Payment row is modified.

## Refund gateway

`RefundGateway` defines `create_refund` and `status`. Only the deterministic
`NullRefundGateway` is installed. It performs no external financial operation and
advances a Refund through processing to completion with append-only provider
transaction records.

Future provider adapters must protect provider credentials and payloads, provide
idempotency, reconcile asynchronous status, and preserve the same application and
transaction boundaries.

## Inventory disposition

Return Items snapshot Order Item Variant, Inventory, quantity, unit price, and
currency. Creation validates Inventory ownership through `InventoryService`.
Inspection records disposition only. Even `RESTOCK` does not mutate Inventory in
this phase; an approved later workflow must interpret disposition and perform any
stock adjustment through InventoryService.

## HTTP API

Return endpoints:

- `POST /api/v1/returns`
- `GET /api/v1/returns`
- `GET /api/v1/returns/{return_id}`
- `PATCH /api/v1/returns/{return_id}`
- `POST /api/v1/returns/{return_id}/approve`
- `POST /api/v1/returns/{return_id}/receive`
- `POST /api/v1/returns/{return_id}/inspect`
- `POST /api/v1/returns/{return_id}/reject`
- `POST /api/v1/returns/{return_id}/cancel`
- `GET /api/v1/returns/{return_id}/summary`

Refund endpoints:

- `POST /api/v1/refunds`
- `GET /api/v1/refunds`
- `GET /api/v1/refunds/{refund_id}`
- `POST /api/v1/refunds/{refund_id}/process`
- `GET /api/v1/refunds/{refund_id}/status`

All routes declare their Return or Refund permission in OpenAPI.

## Events and metrics

Return and Refund events use identifier-only transactional outbox payloads with no
commercial values. Counters cover creation, receipt, rejection, refund completion,
and refunded Returns. An unlabeled histogram measures Refund terminal duration.

## Verification

The production-backed HTTP integration test traverses authentication,
authorization, Store, Catalog, Product, Variant, Inventory, Pricing, Cart,
Checkout, Order, Payment, Reservation, Shipment, Return, Refund, PostgreSQL, and
the transactional outbox. It uses no mocks, fake repositories, monkeypatches, or
direct model insertion.
