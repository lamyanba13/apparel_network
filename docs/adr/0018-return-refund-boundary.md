# ADR 0018: Return and Refund Boundary

- Status: Accepted
- Date: 2026-08-05

## Context

Delivered purchases need auditable item-level Return eligibility, inspection, and
Refund processing. These workflows depend on commercial and fulfillment records
but must not obtain write access to Orders, Shipments, Payments, or Inventory.
Refund providers also require an abstraction before any real provider is selected.

## Decision

Introduce Returns and Refunds as a customer-owned, Store-scoped bounded context.
Return creation validates an owned confirmed Order, delivered Shipment, captured
Payment, immutable Order Items, cumulative refundable quantity, and Inventory
identity through production services.

Return Items snapshot only the fields needed for quantity, disposition, and refund
calculation. Inspection records an explicit disposition without changing stock.
Refunds derive their amount from Return Items, enforce the remaining captured
Payment amount, and use a `RefundGateway` port with a deterministic Null adapter.

Return and Refund transitions, provider transactions, and identifier-only outbox
events share the request transaction. Repositories flush only.

## Consequences

- Cross-context writes remain prohibited.
- Returned quantity cannot exceed purchased quantity across concurrent claims.
- Refund amounts do not depend on mutable current Pricing.
- One Refund per Return prevents duplicate successful reimbursement.
- Failed and completed provider outcomes remain auditable.
- Inventory disposition is recorded without automatic restocking.
- Real provider integration, reconciliation, stock disposition execution, and
  exchange workflows require separate approval.
