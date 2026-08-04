# ADR 0014: Order Boundary

- Status: Accepted
- Date: 2026-08-04

## Context

Shopping Cart represents mutable intent, while Checkout provides revalidated and
frozen customer confirmation data. Downstream Payment and fulfillment workflows
need a durable commercial contract that cannot change when its sources change.

## Decision

Introduce Order as a separate customer-owned, Store-scoped bounded context. An
Order can be created only from a confirmed Checkout Session and exactly one Order
may reference that Session. Creation copies immutable Checkout snapshots and does
not read Cart Items, re-resolve Pricing, or mutate Inventory.

Orders follow `PENDING -> CONFIRMED -> CANCELLED`, use optimistic versions, and
retain immutable Items after soft deletion. Identifier-only lifecycle events share
the PostgreSQL transaction through the existing outbox.

Order numbers use `ORD-YYYYMMDD-NNNNNN`. A non-cycling global PostgreSQL sequence
provides concurrency-safe, unique, gap-tolerant suffixes and the date is UTC. The
six-digit format is limited to 999,999 allocations and requires a new reviewed
numbering decision before exhaustion.

## Consequences

- Orders remain stable when Cart, Pricing, or Inventory changes later.
- Checkout ownership and confirmation are enforced through its production service.
- Sequence gaps are valid and must not be interpreted as missing Orders.
- Confirmation does not process Payment, reserve stock, calculate tax or shipping,
  issue an invoice, or begin fulfillment.
- Later Payment and fulfillment capabilities depend on confirmed Orders without
  extending the Checkout boundary.
