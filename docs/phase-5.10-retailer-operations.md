# Phase 5.10 — Retailer Operations & Inventory Management

## Status

Implemented and validated against the complete Phase 5.10 matrix.

## Operational model

Phase 5.10 extends the existing Store → Catalog → Product → Variant → Inventory
workflow without introducing duplicate product, order, shipment, reservation, or
event boundaries. Product and Variant lifecycle operations continue through their
existing services. Active Store owners and accepted Store staff can operate the
same Store-scoped records; resources outside that boundary remain concealed as
`404`.

The Variant remains the sellable and inventory-bearing unit. PostgreSQL inventory
items remain the authoritative current snapshot. The new movement ledger is an
append-only operational history and is never used to reconstruct current stock on
a request path.

## Explicit inventory operations

`POST /api/v1/inventory/{inventory_id}/adjust` accepts a signed quantity delta,
an allowed movement type, an explanation, the expected version, and an optional
source/reference. Increase, decrease, damage, loss, found-stock, and correction
semantics are validated by the application service.

`POST /api/v1/inventory/{inventory_id}/reconcile` accepts the physical count and
calculates the delta from the locked current snapshot. Callers cannot fabricate a
reconciliation delta. Both operations:

- lock the Inventory row before reading active Reservation capacity;
- reject stale versions with `409 Conflict`;
- reject discontinued Inventory;
- preserve non-negative on-hand and available quantities;
- reject a result below legacy reserved quantity plus active, unexpired holds;
- update audit attribution and optimistic version;
- append one movement record; and
- append identifier-only events to the shared transactional outbox.

The compatibility `PATCH /api/v1/inventory/{id}` remains available for backward
compatibility. Quantity changes through it now use the same locking, reservation
protection, audit attribution, movement persistence, and outbox behavior. New
retailer clients should use the explicit operations.

Shipment dispatch continues to consume stock only through `InventoryService` and
now appends a reservation-consumption movement. Lock ordering remains Inventory
row first, then active Reservation aggregation, matching the established
Inventory/Reservation boundary.

## Movement history

`inventory_movements` records the Inventory, Store, Variant, type, signed delta,
previous/resulting on-hand and available values, protected Reservation quantity,
reason, actor, source, optional reference, and timestamp. The model exposes only
append and read repository operations. Database constraints protect arithmetic
and non-negative state, while foreign keys and compound indexes support scoped,
deterministic queries.

History is available from:

- `GET /api/v1/inventory/{inventory_id}/movements`
- `GET /api/v1/inventory/movements`

Filters cover Store, Inventory, Variant, movement type, time range, actor, source,
and reference. Results order by timestamp and movement identifier descending and
use bounded offset pagination.

## Stock attention and retailer operations

Effective available stock is the current snapshot's available quantity minus
active, unexpired Reservation Items. A value at or below zero is out of stock; a
positive value at or below the configured threshold is low stock. Reads do not
emit events.

- `GET /api/v1/inventory/low-stock`
- `GET /api/v1/inventory/out-of-stock`
- `GET /api/v1/retailer/operations/summary`
- `GET /api/v1/retailer/operations/orders`
- `GET /api/v1/retailer/operations/shipments`

The summary is bounded to one accessible Store and reports active products and
variants, stock classifications, order and fulfillment attention counts, and ten
recent movements. Order and Shipment views are read-only projections with
deterministic pagination; lifecycle mutations remain exclusively in
`OrderService` and `ShipmentService`.

## Events and metrics

Inventory mutations reuse the Phase 5.9 transactional outbox and its structured
logging delegate. No second event bus exists. New identifier-only events are:

- `inventory.adjusted`
- `inventory.reconciled`
- `inventory.low_stock`
- `inventory.out_of_stock`

Threshold events are emitted only when a mutation crosses into the corresponding
state, preventing read-driven event spam. No notification template is added in
this phase; a future notification consumer may subscribe through the existing
event-to-notification boundary.

Low-cardinality metrics count adjustments, reconciliations, low-stock and
out-of-stock crossings, and measure adjustment duration. They contain no actor,
Store, Product, Variant, Inventory, Order, or reference labels.

## Authorization

Existing `inventory:view` and `inventory:update` permissions are sufficient and
remain visible in OpenAPI metadata. No new RBAC migration is required. Store
ownership or accepted active membership is additionally required at the data
boundary. Customers cannot mutate Inventory, and cross-Store reads or mutations
are concealed.

## Known limitations and deferrals

POS, barcode, ERP, supplier synchronization, bulk feeds, forecasting, automated
replenishment, settlement, payouts, accounting, external shipping integration,
and a full retailer frontend remain deferred. Inventory movement history is an
operational ledger, not a general-ledger accounting subsystem. Thresholds are
simple per-Inventory values and do not predict demand.

## Verification contract

Production-backed HTTP/PostgreSQL coverage verifies movement persistence and
audit attribution, adjustment and reconciliation arithmetic, stale conflict,
Reservation protection, threshold queries/events, shared-outbox persistence,
pagination/filtering, Store isolation, accepted staff access, authorization,
summary/order/shipment projections, and OpenAPI permission metadata. Existing
commerce suites remain the regression contract.
