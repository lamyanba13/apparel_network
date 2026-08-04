# Phase 5.0 — Shopping Cart Foundation

## Status

Approved on 2026-08-04 after the complete backend, frontend, migration, API,
static-analysis, and infrastructure validation matrix passed.

## Boundary

Shopping Cart is a customer-owned bounded context inside the modular monolith. It
owns Cart lifecycle, Cart Items, quantities, commercial snapshots, inventory
availability validation, optimistic versions, soft deletion, events, and metrics.
It does not reserve or mutate Inventory and does not create Orders, calculate tax
or shipping, process payments, convert currency, or apply coupons.

## Persistence

`shopping_carts` stores one active Cart per `(user_id, store_id)`. A partial unique
index enforces that invariant without preventing historical checked-out, abandoned,
or expired Carts. `shopping_cart_items` stores one live row per Cart and Variant;
its partial unique index permits a removed Variant to be added again while retaining
soft-deleted history. Both tables use UUIDv7 identifiers, audit attribution,
soft-deletion metadata, and SQLAlchemy optimistic versioning.

Repositories flush only. The FastAPI dependency owns commit and rollback so Cart
state and identifier-only outbox records share one PostgreSQL transaction.

## Lifecycle

The initial status is `active`. An active Cart may transition exactly once to
`checked_out`, `abandoned`, or `expired`. The Phase 5.0 HTTP contract exposes
abandonment through Cart deletion. Checkout and expiration remain application
service transitions for later orchestration; no checkout or order endpoint is
introduced.

## Price snapshots

Adding or changing an Item calls the production `PricingResolver` with the Cart's
Store, Product, Variant, currency, customer group, and current timestamp. The Item
persists the resolved Product Price identifier, fixed-precision amount, currency,
and its mutation timestamp. Reads and summaries use those persisted fields and
never resolve or recalculate an existing snapshot. A later Price change therefore
does not alter an existing Item; changing the Item quantity creates a new snapshot.

No currency conversion occurs. A Cart contains Items in the Cart's explicit
ISO-4217 currency only.

## Inventory validation

Adding or changing an Item calls the production `InventoryService`. The Variant
must be active, belong to the Cart's Store, have an active Inventory record, and
have at least the requested available quantity. The resulting validation snapshot
records the Inventory identifier, version, available quantity, and validation
timestamp. This check does not reserve stock, increment reserved quantity, or
guarantee later checkout availability.

## Ownership and authorization

The API requires `cart:create`, `cart:view`, `cart:update`, or `cart:delete` as
appropriate. Every query and mutation is scoped by the authenticated user ID.
Another user's Cart or Item is represented as `404 Not Found`, preventing resource
enumeration. The migration grants Cart permissions to authenticated platform roles;
guest access is excluded.

## HTTP API

- `POST /api/v1/cart`
- `GET /api/v1/cart`
- `GET /api/v1/cart/{cart_id}`
- `POST /api/v1/cart/{cart_id}/items`
- `PATCH /api/v1/cart/{cart_id}/items/{item_id}`
- `DELETE /api/v1/cart/{cart_id}/items/{item_id}`
- `DELETE /api/v1/cart/{cart_id}`
- `GET /api/v1/cart/{cart_id}/summary`

Mutation contracts carry the relevant Cart or Item version and return `409 Conflict`
for stale versions. The summary returns active Items, persisted-price subtotal,
currency, and total quantity.

## Events and metrics

Cart writes persist `cart.created`, `cart.updated`, `cart.deleted`,
`cart.checked_out`, `cart.expired`, `cart.item_added`, `cart.item_updated`, and
`cart.item_removed` records through the existing transactional outbox. Payloads
contain identifiers, aggregate version, and timestamp only. Phase 5.0 adds counters
for created Carts, added Items, removed Items, checkout transitions, and abandoned
Carts.

## Verification

The production-backed HTTP test creates the complete Store, Catalog, Product,
Variant, Inventory, Pricing, and Cart chain without mocks or direct model inserts.
It covers ownership hiding, lifecycle conflicts, availability checks, snapshot
stability and refresh, summaries, optimistic locking, soft deletion, outbox writes,
and metrics. OpenAPI assertions verify all eight routes and their permissions.
