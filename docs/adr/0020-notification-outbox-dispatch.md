# ADR 0020: Notification Outbox Dispatch Boundary

- Status: Accepted
- Date: 2026-08-08

## Context

Customer communication must react to commerce lifecycle changes without coupling
Order, Payment, Shipment, Return, Refund, or Promotion transactions to provider
availability. Duplicate worker execution must not create duplicate deliveries,
and customer preferences must not suppress required transactional messages.

## Decision

Consume existing identifier-only commerce events from the shared transactional
outbox. A Notifications-owned dispatcher creates one notification per source
event, customer, and channel, applies channel preferences, renders a persisted
plain-text template, and invokes a provider-neutral gateway. The source event is
published only after all applicable notifications are terminal.

Notifications owns delivery attempts, failure history, retry scheduling, read
state, and preferences. Repositories flush only; the worker or HTTP dependency
owns the transaction. Bounded exponential backoff handles transient failures.
Commerce messages ignore marketing opt-out but continue to respect channel flags.
The foundation ships a deterministic network-free Null gateway.

## Consequences

- Commerce transactions remain independent of notification providers.
- At-least-once worker execution is safe at the notification and delivery levels.
- Delivery and failure history remains auditable without exposing destinations in
  domain events.
- Provider replacement requires a gateway adapter, not domain or API changes.
- Outbox backlog reflects notifications still waiting for a retry.
- Real provider credentials, HTML templates, and campaign orchestration remain
  deferred.

Accepted ADRs are immutable historical records. A material change is documented
in a new ADR that supersedes this decision.
