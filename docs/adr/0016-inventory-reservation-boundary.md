# ADR 0016: Inventory Reservation Boundary

- Status: Accepted
- Date: 2026-08-04

## Context

Captured Payments need a temporary claim on ordered stock before Fulfillment, but
Inventory quantities must remain authoritative and Fulfillment is not yet an
approved capability. Directly changing Inventory's reserved quantity would couple
the hold lifecycle to Inventory persistence and contradict this phase boundary.

## Decision

Introduce Inventory Reservation as a separate customer-owned, Store-scoped bounded
context. A Reservation may be created only when a captured Payment, confirmed
Order, and confirmed Checkout share the same ownership chain.

Reservation Items copy Order quantities and validate current active Inventory,
Variant, Store, version, and capacity. Inventory rows are locked in stable order
during validation. Available capacity is calculated by subtracting unexpired
active Reservation Items; no Inventory quantity is updated.

Reservations transition atomically from created to active and then to consumed,
released, or expired. Expiration is lazy with a 30-minute default. Identifier-only
events share the PostgreSQL transaction through the existing outbox.

## Consequences

- Active Reservations hold capacity without becoming Inventory records.
- Concurrent Reservation creation is serialized per Inventory Item and cannot
  oversubscribe the current available quantity.
- Expired holds stop consuming capacity by timestamp even before their event is
  lazily materialized.
- Released and expired Reservations retain history through soft deletion; consumed
  Reservations remain durable for Fulfillment.
- Fulfillment must use application services to consume a Reservation and adjust
  Inventory; it may not update either context's tables directly.
- No scheduler, shipment, invoice, Payment processing, or Inventory adjustment is
  introduced in Phase 5.4.
