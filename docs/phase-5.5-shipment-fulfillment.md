# Phase 5.5 — Shipment & Fulfillment Foundation

## Status

Approved on 2026-08-04 after the complete backend, migration, API,
static-analysis, frontend, and infrastructure validation matrix passed.

## Boundary

Shipment is a customer-owned, Store-scoped fulfillment context. It owns shipment
lifecycle, packages, carrier labels, tracking history, optimistic versions,
transactional events, and delivery metrics. It consumes the durable result of an
Inventory Reservation but never processes Payments, changes Orders, reserves
stock, reads mutable Pricing, or writes Inventory tables.

## Creation and ownership

Creation validates the Payment, Order, and Reservation through their production
application services. Payment must be `CAPTURED`, Order must be `CONFIRMED`, and
Reservation must be `CONSUMED`. Their Order, customer, Store, Payment, and
Reservation identifiers must match. One Shipment may exist per Order and per
Reservation. Cross-user reads and mutations return `404`.

Creation atomically persists `CREATED`, its tracking entry and outbox event, then
advances to `READY_FOR_FULFILLMENT`.

## Lifecycle

```text
CREATED -> READY_FOR_FULFILLMENT -> PACKED -> SHIPPED
        -> OUT_FOR_DELIVERY -> DELIVERED

PACKED -> CANCELLED
SHIPPED -> RETURN_REQUESTED -> RETURNED
```

`DELIVERED`, `RETURNED`, and `CANCELLED` are terminal. There is no reopening.
Cancellation soft-deletes the Shipment while retaining packages, tracking, and
outbox history. Every mutation requires the current optimistic version; stale
requests return `409 Conflict`.

The delivery endpoint advances `SHIPPED` through `OUT_FOR_DELIVERY` and then
`DELIVERED` in the same transaction when a separate carrier callback has not
already materialized the intermediate status.

## Reservation and Inventory interaction

Shipment never modifies a Reservation. Creation requires an already-consumed
Reservation and copies only its identifiers. Dispatch obtains the immutable
Reservation Items through `ReservationService`, then invokes the production
`InventoryService.consume_reservation` workflow.

Inventory rows are locked in stable identifier order. Inventory validates active
status and sufficient on-hand quantity, decrements on-hand and available quantity,
increments the Inventory version, and emits the existing updated and adjusted
events. Shipment repositories have no Inventory persistence access.

## Packages and tracking

Packing requires at least one uniquely numbered package with positive weight and
dimensions. Labels are created through `ShippingGateway`; only the deterministic
`NullShippingGateway` is installed. Package records and labels are immutable.

Every lifecycle materialization appends a tracking event. Tracking reads invoke
the gateway abstraction when a tracking number exists and return persisted
history in chronological order.

## Courier abstraction

`ShippingGateway` defines `create_label`, `cancel_label`, `track`, `estimate`, and
`manifest`. The Null adapter performs no third-party operation and produces stable
foundation values. Future carrier integrations must implement this port, protect
provider credentials and payloads, map callbacks idempotently, and preserve the
same application lifecycle and transaction boundaries.

## HTTP API

- `POST /api/v1/shipments`
- `GET /api/v1/shipments`
- `GET /api/v1/shipments/{shipment_id}`
- `POST /api/v1/shipments/{shipment_id}/pack`
- `POST /api/v1/shipments/{shipment_id}/ship`
- `POST /api/v1/shipments/{shipment_id}/deliver`
- `POST /api/v1/shipments/{shipment_id}/cancel`
- `GET /api/v1/shipments/{shipment_id}/tracking`

Routes require `shipment:create`, `shipment:view`, `shipment:update`,
`shipment:ship`, or `shipment:deliver` as appropriate.

## Events and metrics

Shipment lifecycle events use identifier-only transactional outbox payloads:
`shipment.created`, `shipment.packed`, `shipment.shipped`,
`shipment.out_for_delivery`, `shipment.delivered`, `shipment.cancelled`,
`shipment.return_requested`, and `shipment.returned`.

Created, packed, shipped, delivered, and cancelled counters plus an unlabeled
delivery-duration histogram provide low-cardinality observability.

## Verification

The production-backed HTTP integration test traverses authentication,
authorization, Store, Catalog, Product, Variant, Inventory, Pricing, Cart,
Checkout, Order, Payment, Reservation, Shipment, PostgreSQL, and the transactional
outbox. It uses no mocks, fake repositories, monkeypatches, or direct model
insertion.
