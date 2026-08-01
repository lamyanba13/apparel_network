# Phase 4.0 — Catalog Foundation

Status: implemented, pending review
Date: 2026-08-01

## Scope

Catalog is the first Phase 4 bounded context. It owns catalog metadata only;
Products, variants, inventory, pricing, reservations, and media remain outside
this phase. PostgreSQL is authoritative and the existing Identity, Store,
authorization, RabbitMQ, Redis, and search boundaries remain unchanged.

## Data model

`catalogs` uses UUIDv7 identifiers and contains `store_id`, name, slug,
description, lifecycle status, visibility, sort order, timestamps, soft-delete
metadata, optimistic version, and actor audit fields. Slugs are unique within a
Store. Version is positive, sort order is non-negative, and deleted rows must
be archived. The migration adds Store-scoped indexes for listing, filtering,
ordering, and slug lookup.

`sort_order` is the public display-order field. Catalogs also retain
`activated_at`, `archived_at`, and an `is_default` flag. At most one active,
non-deleted default catalog is allowed per Store.

## Lifecycle and ownership

Catalogs begin as Draft and may become Active or Archived. Archived catalogs
cannot return to Draft or Active. DELETE is a soft-delete operation that
archives the record. Every read and write is scoped through the owning Store;
cross-store access returns the same 404 response as a missing resource.
Optimistic versions prevent lost updates. Repositories flush but never commit;
the HTTP transaction dependency owns commit and rollback.

## API

- `POST /api/v1/catalogs` creates a Store-owned catalog.
- `GET /api/v1/catalogs` lists non-deleted catalogs for owned Stores.
- `GET /api/v1/catalogs/{catalog_id}` returns one owned catalog.
- `PATCH /api/v1/catalogs/{catalog_id}` updates editable metadata with a
  required version.
- `DELETE /api/v1/catalogs/{catalog_id}?version=N` archives and soft-deletes.

Permissions are `catalog:create`, `catalog:view`, and `catalog:update`. No role
names are compared in application code.

## Events and metrics

Catalog events contain only catalog ID, Store ID, version, and event timestamp:
`CatalogCreated`, `CatalogUpdated`, `CatalogArchived`, and `CatalogDeleted`.
`CatalogActivated` and `CatalogVisibilityChanged` are reserved event types for
future consumers.
Descriptions, names, and user content are never included. Label-free counters
track created, updated, deleted, and archived operations.

## Migration and validation

Migration `a91c7d4e2f10_create_catalogs.py` is linear, reversible, and has no
external infrastructure dependency. Upgrade, downgrade, re-upgrade, and
Alembic drift checks are required before release. Catalog tests cover validation,
ownership, optimistic locking, soft deletion, events, metrics, and API
contract behavior.
