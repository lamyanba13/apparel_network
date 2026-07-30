# ADR 0002: RabbitMQ as the Celery Broker

- Date: 2026-07-30
- Status: Accepted

## Context

Background work needs queue semantics, acknowledgements, routing, retry handling, and operational visibility. Redis is already required for latency-sensitive ephemeral functions. Using one component for unrelated responsibilities would couple cache pressure and eviction behavior to job delivery.

## Decision

Use RabbitMQ as the exclusive Celery message broker.

Redis is limited to caching, sessions, rate limiting, temporary reservation locks, and ephemeral coordination. Redis must not be configured as the Celery broker or as durable business storage.

Tasks must be idempotent, declare bounded retry behavior, and acknowledge work according to the task's safety requirements. RabbitMQ transports work; PostgreSQL remains authoritative for business state.

## Alternatives considered

- Redis as the Celery broker: rejected because it couples ephemeral data workloads to task transport and provides less purpose-built broker behavior.
- PostgreSQL-backed polling: rejected because it adds database load and requires a custom queue lifecycle.
- A managed cloud queue: deferred until provider and operating requirements justify the additional integration.

## Consequences

- Queue workloads and Redis latency-sensitive workloads have separate failure and capacity domains.
- RabbitMQ adds an infrastructure component that requires credentials, monitoring, backups of configuration where applicable, and operational runbooks.
- Broker availability does not make a completed task equivalent to a committed business transaction; application state still requires database-backed idempotency and reconciliation.
- Production deployments must configure durable queues, dead-letter behavior, connection security, and capacity alerts.
