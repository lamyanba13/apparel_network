# Phase 4.5 — Inventory Foundation

Status: implemented; E1 integration validation and optimistic-lock compliance complete

Inventory establishes PostgreSQL as the authoritative record for one Product
Variant at one Store. `inventory_items` stores on-hand, reserved, and derived
available quantities with database constraints, optimistic locking, soft
deletion, tenant ownership checks, and identifier-only domain events.

The API exposes create, list, detail, update, and soft-delete operations at
`/api/v1/inventory`, reusing `catalog:view` and `catalog:update`. Reservations,
movements, multiple locations, search integration, and preorder behaviour are
explicitly outside this foundation.

## E1 integration validation

The reusable integration fixture hierarchy now creates an authenticated identity,
a verified Store, a draft Catalog, a draft Product, and a canonical Product Variant
through production application services. Fixtures run against one Alembic-migrated
PostgreSQL database while preserving a clean, rollback-isolated session for every
test. The FastAPI fixtures execute the production lifespan, and restore the
production event publisher logger after Alembic logging configuration.

The Inventory integration test exercises `POST /api/v1/inventory` through the real
FastAPI router, authentication and authorization dependencies, `InventoryService`,
the SQLAlchemy repository, and PostgreSQL. It verifies the response contract,
variant and Store associations, quantities, optimistic version, audit fields,
persisted database state, the existing `inventory.created` structured event, and
the Prometheus creation counter.

E1 exposed persistence-boundary defects where transient service values were being
forwarded to SQLAlchemy model constructors. Catalog, Product, and Product Variant
repositories now map `actor_id` to their existing `created_by_id` and
`updated_by_id` audit columns. Inventory persistence excludes transient context
values while retaining its explicit audit-column mapping. These corrections did
not change API, DTO, lifecycle, event, or migration contracts.

## Phase 4.5.1 optimistic-lock compliance

Production-backed HTTP integration coverage now exercises Inventory detail, list,
update, and delete routes in addition to creation. Successful PATCH and DELETE
requests use the current version and advance the persisted optimistic version.
Stale PATCH and DELETE requests return `409 Conflict`; rejected stale deletes leave
the Inventory record active and unchanged. Owner-scoped missing records continue to
return `404 Not Found` without exposing cross-Store data.

## Phase 5.10 operational extension

Phase 5.10 preserves this authoritative snapshot and compatibility API while
adding explicit adjustment and physical-count reconciliation commands,
append-only movement history, active-Reservation protection, accepted Store-staff
access, and retailer stock-attention queries. See
[`phase-5.10-retailer-operations.md`](phase-5.10-retailer-operations.md) and
[`ADR 0022`](adr/0022-retailer-inventory-operations.md).
