# Phase 4.1 — Product Foundation

Status: implemented, pending review

## Scope

Products begin inside the Catalog bounded context. Each Product belongs to one
Catalog and one Store. This phase excludes variants, inventory, pricing, media,
reservations, and search indexing.

## Model and invariants

Products use UUIDv7 identifiers, Store and Catalog foreign keys, lifecycle
status, visibility, SKU, slug, descriptions, brand, ordering, soft deletion,
optimistic versioning, and audit actor fields. Catalog-scoped slugs and
Store-scoped SKUs are unique among non-deleted records. Archived Catalogs
cannot accept new Products. Product deletion archives and soft-deletes.

## Lifecycle and ownership

Products follow Draft → Active → Archived. Archived Products cannot return to
Draft. Every repository query joins the owning Store, so cross-store access is
returned as 404. Repositories flush only; HTTP dependencies own commit and
rollback.

## API

- `POST /api/v1/products`
- `GET /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `PATCH /api/v1/products/{product_id}`
- `DELETE /api/v1/products/{product_id}?version=N`

List filters include `catalog_id`, `status`, `visibility`, `offset`, and
`limit`. Existing `catalog:view` and `catalog:update` permissions are reused;
no role-name checks are introduced.

## Events and metrics

`ProductCreated`, `ProductUpdated`, `ProductArchived`, and `ProductDeleted`
contain only Product ID, Catalog ID, Store ID, version, and event metadata.
Descriptions, SKU values, and user content are excluded.

Metrics are label-free:

- `fashion_network_product_created_total`
- `fashion_network_product_updated_total`
- `fashion_network_product_deleted_total`
- `fashion_network_product_archived_total`

## Migration and boundaries

Migration `c83f1a9e2d04_create_products.py` creates the Product table and
required constraints/indexes. Product persistence references Catalog and Store
only; Identity, authentication, authorization, search, analytics, Docker,
RabbitMQ, and Redis architecture remain unchanged.
