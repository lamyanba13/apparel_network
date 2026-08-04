# ADR 0017: Shipment and Fulfillment Boundary

- Status: Accepted
- Date: 2026-08-04

## Context

Captured Orders with consumed Reservations need auditable package, dispatch,
tracking, delivery, cancellation, and future return workflows. Shipment must not
become an alternative owner for Payment, Order, Reservation, or Inventory data.
Carrier integrations also need a stable application-facing boundary before any
provider is selected.

## Decision

Introduce Shipment as a customer-owned, Store-scoped bounded context. Creation
requires a captured Payment, confirmed Order, and consumed Reservation with a
matching ownership chain. Shipment owns packages, tracking history, lifecycle,
optimistic versions, outbox events, and metrics.

Dispatch invokes a production Inventory application workflow using immutable
Reservation Items. Only Inventory repositories lock and update Inventory rows.
Shipment never writes Inventory or Reservation tables and never processes a
Payment or mutates an Order.

Define `ShippingGateway` with label, cancellation, tracking, estimate, and manifest
operations. Install only a deterministic Null adapter. Persist lifecycle events in
the existing transactional outbox with identifier-only payloads.

## Consequences

- Fulfillment remains independently evolvable from commercial and stock records.
- Dispatch and Inventory consumption commit or roll back together.
- One Shipment per Order and Reservation prevents duplicate fulfillment records.
- Packages and tracking history remain auditable after terminal transitions.
- Carrier-specific APIs and credentials cannot leak into domain or API contracts.
- Future carrier callbacks require idempotency and explicit lifecycle mapping.
- Shipment cancellation does not restore Inventory because cancellation is allowed
  only before dispatch.
- Returns and stock restoration require a separately approved workflow.
