# Fashion Network

Fashion Network is a searchable digital inventory network for existing clothing stores in Manipur. It helps customers discover which participating store currently carries a product while each store keeps ownership and physical control of its inventory.

The `docs/` directory is the source of truth for product and technical
decisions. The `foundation-v1` baseline remains frozen; Identity was completed
and frozen in Phase 2.6. Phases 3.1 through 3.4 add the isolated Store profile,
verification, staff-management, and media subdomains.

## Product boundary

Fashion Network:

- indexes inventory supplied by participating stores;
- lets customers search and filter products across stores;
- lets authorized store personnel maintain store, product, and stock data;
- lets customers create time-limited reservations;
- gives administrators the controls required to operate the network.

Fashion Network is not an e-commerce merchant, marketplace seller, warehouse, payment processor, delivery provider, or owner of store inventory. Stores remain responsible for product accuracy, reservation fulfillment, and any transaction that occurs at the store.

## Architecture at a glance

The system is a modular monolith with three deployable applications:

- `frontend/`: public customer experience built with Next.js, React, TypeScript, and TailwindCSS.
- `dashboard/`: store and administrator experience using the same frontend stack.
- `backend/`: FastAPI application containing feature modules and asynchronous Celery workers.

PostgreSQL is the system of record. Meilisearch is a rebuildable search projection. Redis supports caching, rate limiting, and short-lived coordination. RabbitMQ is the durable Celery broker, keeping cache eviction and broker durability concerns separate. Cloudflare R2 stores uploaded media.

The backend modules are Auth, Users, Stores, Products, Inventory, Reservations, Search, Notifications, Admin, Audit, Analytics, and Uploads. Module boundaries are enforced in code even though the modules deploy together. The reviewed OpenAPI contract is the client/server source of truth; FastAPI must implement and continuously conform to it.

## Documentation map

Read these documents in order when joining the project:

1. [Vision](01-vision.md)
2. [Business Requirements](02-business-requirements.md)
3. [Functional Requirements](03-functional-requirements.md)
4. [Non-functional Requirements](04-non-functional-requirements.md)
5. [Technology Stack](05-technology-stack.md)
6. [System Architecture](06-system-architecture.md)
7. [Folder Structure](07-folder-structure.md)
8. [Coding Standards](08-coding-standards.md)
9. [API Standards](09-api-standards.md)
10. [Security Standards](10-security-standards.md)
11. [Deployment Strategy](11-deployment-strategy.md)
12. [Development Roadmap](12-development-roadmap.md)
13. [Sprint Plan](13-sprint-plan.md)
14. [Risk Analysis](14-risk-analysis.md)
15. [Scaling Strategy](15-scaling-strategy.md)
16. [Contributing Guide](16-contributing-guide.md)
17. [Git Workflow](git-workflow.md)
18. [Local Development Environment](local-development.md)
19. [Phase 0 Architecture Review](PHASE0_REVIEW.md)
20. [Observability](observability.md)
21. [Platform Runbook](runbook.md)
22. [Backups](backups.md)
23. [Disaster Recovery](disaster-recovery.md)
24. [Resource Limits](resource-limits.md)
25. [Development Performance Baseline](performance-baseline.md)
26. [Production Deployment Checklist](production-deployment-checklist.md)
27. [Dependency Report](dependency-report.md)
28. [Architecture Decision Records](adr/README.md)
29. [Foundation Architecture Diagrams](architecture-diagrams.md)
30. [Phase 1.6 Architecture Freeze Review](phase-1.6-architecture-freeze.md)
31. [Phase 2.3 Session Management](phase-2.3-session-management.md)
32. [Phase 2.4 Authorization](phase-2.4-authorization.md)
33. [Phase 2.5 Account Security](phase-2.5-account-security.md)
34. [Phase 2.6 Identity Module Freeze](phase-2.6-identity-freeze.md)
35. [Identity Enterprise Review](identity-enterprise-review.md)
36. [Phase 3.1 Store Domain](phase-3.1-store-domain.md)
37. [Phase 3.2 Store Verification](phase-3.2-store-verification.md)
38. [Phase 3.3 Store Staff Management](phase-3.3-store-staff-management.md)
39. [Phase 3.4 Store Media](phase-3.4-store-media.md)

## Decision authority

The documents use the terms **MUST**, **SHOULD**, and **MAY** as defined by RFC 2119-style convention:

- **MUST** is required for correctness, security, or an accepted architectural decision.
- **SHOULD** is the default unless a documented trade-off justifies an exception.
- **MAY** is optional.

If documents appear to conflict, apply this precedence:

1. product boundary and business requirements;
2. security and data-integrity requirements;
3. system architecture and API standards;
4. coding and contribution conventions;
5. roadmap and sprint sequencing.

An architecture decision that changes a MUST requirement requires an Architecture Decision Record (ADR), review by the technical owner, and corresponding updates to every affected document.

## Shared definitions

| Term               | Meaning                                                                  |
| ------------------ | ------------------------------------------------------------------------ |
| Store              | A participating physical clothing retailer in Manipur.                   |
| Store owner        | The principal user responsible for a store account and staff access.     |
| Store staff        | A user invited to operate permitted parts of a store account.            |
| Product            | Merchandising information describing an item or style.                   |
| Variant            | A specific selectable combination, normally size and color.              |
| Inventory item     | Store-specific stock for a product variant.                              |
| Available quantity | Quantity eligible for a new reservation after active holds are deducted. |
| Reservation        | A time-limited hold requested by a customer for inventory at one store.  |
| Search document    | A denormalized, rebuildable representation in Meilisearch.               |
| System of record   | PostgreSQL data whose committed state is authoritative.                  |

## Initial delivery assumptions

- The launch region is Manipur.
- The first production release is a responsive web platform.
- One user may be associated with more than one store.
- A first-release reservation holds one product variant from one store.
- Inventory is changed manually through the dashboard in the initial release. Bulk import is P1 after the controlled pilot; third-party POS integrations are not assumed.
- Search freshness is near-real-time but not transactional.
- Payments, shipping, delivery, checkout, commissions, and platform-owned fulfillment are outside scope.
- The initial architecture is sized for 1,000 stores, load-tested against the documented first capacity profile, and has explicit evolution gates for 10,000 and 100,000 stores.

## Definition of ready for development

Development can begin when:

- product and technical owners approve the business and functional requirements;
- open decisions explicitly listed in the roadmap have owners and due dates;
- environments, secrets ownership, and production service providers are approved;
- the initial data dictionary, relationship/index plan, and OpenAPI-first contract skeleton are reviewed;
- security threat modeling is completed for authentication, uploads, authorization, reservations, and administrative actions;
- the RabbitMQ, OpenTofu, OpenTelemetry, metrics, logging, and local-development decisions in the reviewed stack are reflected in Sprint 0;
- the first two sprints meet the readiness criteria in the sprint plan.
