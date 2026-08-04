# ADR 0015: Payment Boundary

- Status: Accepted
- Date: 2026-08-04

## Context

A confirmed commercial purchase requires a provider-neutral Payment capability,
but the platform has not approved a real provider, refunds, settlements, invoices,
or fulfillment. Orders must remain authoritative commercial contracts and Payment
must not acquire ownership of Order persistence or Checkout logic.

## Decision

Introduce Payment as a separate customer-owned, Store-scoped bounded context.
Payment Intents may be created only for owned pending Orders and snapshot the Order
amount, currency, customer, and Store. Intent creation requires a PostgreSQL-backed
customer idempotency key.

The application depends on a `PaymentGateway` protocol. Phase 5.3 installs only a
deterministic Null adapter. Provider interactions create append-only private
transaction records. Lifecycle events use the existing transactional outbox.

Payments follow `CREATED -> AUTHORIZED -> CAPTURED`, with `FAILED` and `CANCELLED`
terminal exits from created or authorized state. Cancellation soft-deletes the
Intent. Successful capture confirms the Order exclusively through `OrderService`;
Payment repositories never write Order tables.

## Consequences

- Payment can evolve independently from Checkout and Order persistence.
- Duplicate Intent commands are safely replayed for the same customer and Order.
- The Null adapter validates orchestration without making a financial transaction.
- Provider payloads remain persistence-private and identifier-only events remain
  safe for the outbox.
- A real gateway requires provider-side idempotency, signed webhooks,
  reconciliation, secret controls, and recovery for external/local transaction
  boundaries before it can replace the Null adapter.
- Inventory, shipping, invoices, refunds, and settlements remain out of scope.
