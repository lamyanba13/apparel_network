# ADR 0012: Shopping Cart Design

- Status: Accepted
- Date: 2026-08-04

## Context

Customers need a durable, Store-scoped collection of intended purchases before
Order, payment, tax, shipping, and reservation capabilities exist. Prices may
change after an Item is added, and Inventory availability may change independently.
The Cart must preserve what was selected without claiming stock ownership or
silently changing historical commercial values.

## Decision

Create Shopping Cart as a customer-owned bounded context with one active Cart per
user and Store. Persist Cart Items with the resolved Product Price identifier,
amount, currency, and snapshot timestamp. Summaries use the stored snapshot and do
not invoke Pricing on reads. Add and quantity-update operations invoke the existing
PricingResolver and InventoryService; Inventory is validated but never reserved.

Use optimistic versions for Cart and Item mutations, soft deletion for abandonment
and Item removal, and `404 Not Found` for cross-user access. Persist identifier-only
Cart events in the existing transactional outbox in the same transaction as the
aggregate write.

The domain supports terminal `checked_out` and `expired` transitions, but Phase 5.0
does not expose checkout orchestration. A future Order or checkout phase must
revalidate price and Inventory, acquire stock through an approved Inventory
contract, and define its own transaction and idempotency policy.

## Consequences

- Existing Cart totals remain stable when Product Prices change.
- Quantity changes deliberately refresh both price and inventory snapshots.
- Availability validation is advisory until a later reservation/checkout boundary.
- Soft-deleted rows preserve audit history while partial unique indexes allow a new
  active Cart or a re-added Variant.
- Cart creation and mutations require an available PostgreSQL transaction and the
  existing Pricing and Inventory application services.
- Currency conversion, discounts, tax, shipping, payment, Orders, and stock holds
  remain explicitly outside this bounded context.

