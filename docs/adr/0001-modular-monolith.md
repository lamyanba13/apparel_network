# ADR 0001: Modular Monolith

- Date: 2026-07-30
- Status: Accepted

## Context

Fashion Network requires clear domain ownership for Auth, Users, Stores, Products, Inventory, Reservations, Search, Notifications, Admin, Analytics, and Uploads. The startup also needs fast delivery, simple operations, transactional consistency, and an architecture that a small team can operate safely. Independent service deployment is not presently a business requirement.

## Decision

Build the backend as a modular monolith. It is one deployable FastAPI application with one PostgreSQL system of record, while Celery workers run background application tasks from the same codebase.

Each feature module owns its application and domain behavior. Clean Architecture dependency direction applies: delivery and infrastructure depend on application abstractions, and domain rules do not depend on FastAPI, SQLAlchemy, Celery, or external providers. Cross-module access occurs through explicit services or contracts rather than direct access to another module's repository internals.

Frontend, dashboard, backend, and infrastructure remain separate monorepo workspaces, but they do not constitute microservices.

## Alternatives considered

- Microservices: rejected because deployment, networking, data ownership, tracing, and failure-mode costs are unjustified at the current scale.
- A traditional layer-only monolith: rejected because global controllers, services, and repositories make domain ownership erode as the product grows.
- A distributed monolith: rejected because it combines service operational cost with tightly coupled releases.

## Consequences

- Local development, deployment, transactions, and debugging remain comparatively simple.
- Module boundaries must be enforced through reviews, tests, imports, and ownership conventions.
- The backend scales initially as a unit, although web and worker processes can scale independently.
- A defect or resource problem can affect the whole backend process.
- Extracting a module later requires evidence, an explicit contract, clear data ownership, and a superseding ADR.
