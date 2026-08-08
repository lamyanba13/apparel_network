# ADR 0021: Commerce Event Reliability

- Status: Accepted
- Date: 2026-08-08
- Supersedes operational details in ADR 0020; its notification boundary remains
  accepted.

## Context

The shared transactional outbox already prevents commerce state from committing
without its event, and Notifications already consumes those events idempotently.
The original row-lock-only dispatcher did not retain claim ownership, lease,
attempt, terminal failure, or recovery metadata. Inventory and Pricing also used
an in-process publisher rather than the shared durable outbox.

## Decision

Keep PostgreSQL as the durable source of truth and harden the existing outbox.
Represent processing with persisted claims and expiring leases, claim eligible
rows with `FOR UPDATE SKIP LOCKED`, use deterministic bounded exponential
backoff, preserve exhausted failures, and record unique consumer receipts.

Use the same request transaction for business state and event creation. Wire
Inventory and Pricing through a shared transactional publisher without changing
their event contracts or structured logging. Keep Notifications as a PostgreSQL
consumer invoked through Celery; do not add Kafka or a second outbox. RabbitMQ
failure can delay work but cannot remove committed events.

Expose only failed or stale records through an `admin:access` inspection and
recovery API. Recovery returns an eligible record to pending and never edits its
payload. Record low-cardinality lifecycle metrics without payload, aggregate ID,
event ID, worker ID, or error labels.

## Consequences

- Concurrent workers skip claims held by another transaction.
- Rolled-back claims remain pending; committed abandoned claims expire.
- Failed events retain attempts, worker, timing, and sanitized error data.
- Repeated notification consumption remains logically idempotent and gains a
  durable consumer receipt.
- Broker outages delay task delivery while PostgreSQL retains source events.
- Operators can inspect and recover failures without direct SQL.
- The outbox schema requires a forward and reversible migration.

