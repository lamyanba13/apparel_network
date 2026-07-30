# ADR 0003: PostgreSQL as the System of Record

- Date: 2026-07-30
- Status: Accepted

## Context

Stores, inventory, and future reservations require constraints, transactions, concurrency control, auditable migrations, and reliable relational queries. Search, cache, and message-broker data are projections or transient coordination and cannot be authoritative.

## Decision

Use PostgreSQL as the authoritative transactional database. Use SQLAlchemy for persistence mapping and Alembic for reviewed, forward migrations.

Relational constraints enforce invariants wherever practical. Runtime access uses the asynchronous PostgreSQL driver; migration and operational tooling may use the appropriate synchronous driver. JSONB is used only for genuinely flexible attributes, not as a substitute for owned relational schemas.

## Alternatives considered

- MySQL: viable, but PostgreSQL better matches the team's selected tooling and anticipated transactional and indexing needs.
- A document database: rejected because the core domain is relational and requires strong cross-record invariants.
- Event sourcing as the primary persistence model: rejected as unnecessary complexity without a demonstrated audit or temporal-reconstruction requirement.

## Consequences

- The platform gains mature transactions, locking, constraints, indexing, and operational tooling.
- Schema changes require backward-compatible migration planning and rollback or roll-forward procedures.
- Connection pools and slow queries must be measured and bounded.
- Scaling begins with query/index optimization and vertical capacity, then read replicas or partitioning only when measurements justify them.
