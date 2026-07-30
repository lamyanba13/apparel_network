# Architecture Decision Records

Architecture Decision Records (ADRs) preserve the reasoning behind foundational technical choices. They complement the normative architecture documents; they do not replace them.

## Lifecycle

- `Proposed`: under review and not yet binding.
- `Accepted`: approved and part of the architecture baseline.
- `Deprecated`: retained for history but no longer recommended.
- `Superseded`: replaced by a later ADR, which must be linked from both records.

Accepted ADRs are immutable historical records. A material change is documented in a new ADR that supersedes the prior decision.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith | Accepted |
| [0002](0002-rabbitmq-over-redis.md) | RabbitMQ as the Celery broker | Accepted |
| [0003](0003-postgresql.md) | PostgreSQL as the system of record | Accepted |
| [0004](0004-fastapi.md) | FastAPI for the backend | Accepted |
| [0005](0005-meilisearch.md) | Meilisearch for search projections | Accepted |
| [0006](0006-minio.md) | MinIO for local object-storage development | Accepted |
| [0007](0007-opentelemetry.md) | OpenTelemetry for distributed telemetry | Accepted |
| [0008](0008-observability.md) | Layered observability strategy | Accepted |
