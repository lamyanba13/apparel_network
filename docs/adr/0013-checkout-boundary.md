# ADR 0013: Checkout Boundary

- Status: Accepted
- Date: 2026-08-04

## Context

A Shopping Cart is mutable intent and its commercial snapshots may predate customer
confirmation. A future Order requires a stable input, but Order creation, Inventory
reservation, payment, tax, shipping, and invoicing are not yet approved capabilities.
The system therefore needs a boundary that revalidates the Cart without prematurely
owning those later workflows.

## Decision

Introduce a customer-owned Checkout bounded context. Checkout creation accepts an
owned active non-empty Cart, re-resolves each current price through `PricingResolver`,
revalidates each quantity through `InventoryService`, and persists immutable Session
and Item snapshots. Exactly one Checkout Session may reference a Cart.

An active Session may be confirmed, expired, or cancelled. Confirmation transitions
the source Cart to `checked_out` in the same PostgreSQL transaction. Cancellation
soft-deletes the Session while retaining Item snapshots. Identifier-only lifecycle
events use the existing transactional outbox. All customer access is owner-scoped,
and stale writes use optimistic versions.

## Consequences

- Checkout totals do not change when Pricing or Cart data changes later.
- Inventory is validated but never reserved, so future Order processing must check
  and acquire stock through an approved Inventory contract.
- Confirmation prepares immutable Order input but does not create an Order or accept
  payment.
- A cancelled or expired Cart cannot open another Checkout because Cart-to-Checkout
  uniqueness preserves an unambiguous history.
- Checkout depends synchronously on the public Cart, Pricing, and Inventory
  application services and transactionally on PostgreSQL and the existing outbox.

