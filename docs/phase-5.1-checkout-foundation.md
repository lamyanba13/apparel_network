# Phase 5.1 — Checkout Foundation

## Status

Approved on 2026-08-04 after the complete backend, frontend, migration, API,
static-analysis, and infrastructure validation matrix passed.

## Boundary

Checkout is a customer-owned bounded context that validates an active Shopping
Cart and freezes the commercial data required by a future Order handoff. It owns
Checkout Session lifecycle, final price and Inventory validation, immutable Item
snapshots, customer confirmation, optimistic versions, cancellation, events, and
metrics.

Checkout does not create Orders, reserve or mutate Inventory, process Payments,
calculate Shipping or Taxes, or generate Invoices.

## Persistence

`checkout_sessions` has one immutable-history Session per Cart. It stores customer
and Store ownership, currency, frozen subtotal, lifecycle timestamps, audit fields,
soft-deletion metadata, and an optimistic version. `checkout_session_items` stores
the Product and Variant, quantity, resolved Price ID and amount, Inventory ID and
version, and separate price and Inventory snapshot timestamps.

Checkout Items expose no update or delete operation. Their unique
`(checkout_session_id, variant_id)` constraint and foreign keys protect the frozen
commercial shape. Repositories flush only; FastAPI owns the transaction containing
the Session, Items, Cart confirmation transition, and outbox writes.

## Cart to Checkout boundary

Creation loads the Cart through the production Cart application service and checks
that it belongs to the authenticated customer, remains `active`, has not expired,
and contains at least one Item. Another customer's Cart resolves as `404 Not Found`.
Only one Checkout Session may ever reference a Cart.

Each Cart Item is revalidated rather than copying its earlier Cart snapshots:

1. The Variant must remain active and belong to the Cart's Store.
2. The production `PricingResolver` selects the current explicit price.
3. The production `InventoryService` verifies current availability.
4. Checkout persists new immutable price and Inventory snapshots.

Changing Pricing, Inventory, or the Cart after creation does not mutate the frozen
Checkout data.

## Lifecycle

The initial status is `active`. An active Session may become `confirmed`, `expired`,
or `cancelled`. Confirmation records `completed_at` and transitions the source Cart
to `checked_out` in the same transaction. Cancellation soft-deletes the Session but
retains its immutable Items. Accessing an overdue active Session materializes the
`expired` transition and its outbox event.

Confirmed, expired, and cancelled Sessions cannot be modified. Stale confirmation
or cancellation versions return `409 Conflict`.

## HTTP API

- `POST /api/v1/checkout`
- `GET /api/v1/checkout`
- `GET /api/v1/checkout/{checkout_id}`
- `POST /api/v1/checkout/{checkout_id}/confirm`
- `DELETE /api/v1/checkout/{checkout_id}`
- `GET /api/v1/checkout/{checkout_id}/summary`

The API requires `checkout:create`, `checkout:view`, `checkout:update`, or
`checkout:confirm`. All reads and writes are scoped to the authenticated customer;
cross-user access returns `404`.

## Events and metrics

Checkout persists `checkout.created`, `checkout.confirmed`, `checkout.expired`, and
`checkout.cancelled` through the existing transactional outbox. Payloads contain
only Checkout, Cart, user, and Store identifiers, aggregate version, and timestamp.

Low-cardinality counters cover created, confirmed, cancelled, and expired Checkout
Sessions.

## Future Order handoff

A later Order phase may consume only a confirmed Checkout Session and its immutable
Items. It must define its own idempotency, Inventory reservation, tax, shipping,
payment, and Order transaction policies. Checkout confirmation alone makes no stock
hold and no purchase commitment outside the frozen data record.

## Verification

The production-backed HTTP test constructs Store, Catalog, Product, Variant,
Inventory, Pricing, Cart, and Checkout state through production services. It covers
empty Cart rejection, current availability failure, price re-resolution, snapshot
immutability, ownership hiding, optimistic confirmation and cancellation, Cart
transition, soft deletion, outbox payloads, metrics, summaries, and OpenAPI.
