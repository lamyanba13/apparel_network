# ADR 0022: Retailer Inventory Operations and Movement Ledger

- Status: Accepted
- Date: 2026-08-08

## Context

The Inventory current-state record supported optimistic CRUD and Shipment
consumption, but manual quantity changes lacked a durable operation-level history.
Retailers need explicit adjustment and physical-count workflows without
invalidating active customer Reservations. Reconstructing current Inventory from
an event stream would replace an established authoritative snapshot and add
unnecessary complexity.

## Decision

Keep `inventory_items` as the authoritative current snapshot and add an
append-only `inventory_movements` operational ledger. All quantity mutations pass
through `InventoryService`, lock the Inventory row, verify the expected version,
then inspect active unexpired Reservations in that stable order. A mutation that
would place on-hand stock below protected quantities is rejected.

Adjustment commands provide a validated signed delta. Reconciliation commands
provide a physical count and the service derives the delta from locked state.
Both update the snapshot, append the movement, and append identifier-only events
to the existing Phase 5.9 outbox in the request-owned transaction. Repositories
remain flush-only.

Use existing `inventory:view` and `inventory:update` permissions plus a shared
Store-access predicate that accepts the owner or an active accepted member. Order
and Shipment operational views are read-only projections; their lifecycle writes
remain within their owning services.

## Consequences

- Current stock remains efficient to read and protected by database invariants.
- Every quantity change has actor, reason, source, before/after state, and time.
- Physical reconciliation cannot overwrite a concurrent change silently.
- Manual operations cannot reduce stock below protected Reservation capacity.
- Movement storage grows monotonically and requires indexed, bounded queries.
- Existing generic Inventory PATCH remains compatible but records protected
  legacy-update movements when quantities change.
- Future POS or ERP adapters can become command sources without bypassing the
  Inventory service or introducing another ledger/event system.
