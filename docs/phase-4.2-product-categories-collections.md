# Phase 4.2 — Product Categories and Collections

## Scope

The Catalog bounded context now provides store-scoped categories and collections. Products may be assigned to either taxonomy, while product ownership remains in the Product module. No authentication, authorization, store, inventory, or search behavior was changed.

## Persistence

- `categories`: hierarchical, store-scoped names and slugs with status, visibility, ordering, soft deletion, and optimistic versioning.
- `collections`: curated store-scoped groups with the same lifecycle metadata.
- `product_categories`: composite-key many-to-many bridge.
- `collection_products`: composite-key bridge with non-negative `display_order`.

Store/slug uniqueness is enforced by database constraints and normalized before validation. Category parent references must remain within the same store and hierarchy cycles are rejected. Archived or deleted taxonomy entities cannot receive products.

## API

All routes are under `/api/v1` and require the existing `catalog:view` or `catalog:update` permission. Create/update requests use typed Pydantic schemas and optimistic `version` values. Repository methods flush only; the route transaction dependency commits successful requests and rolls back failures.

Categories: `POST/GET /categories`, `GET/PATCH/DELETE /categories/{id}`, and product assignment/removal routes.

Collections: `POST/GET /collections`, `GET/PATCH/DELETE /collections/{id}`, product assignment/removal, and optimistic reorder.

## Events and metrics

Lifecycle, assignment, removal, and reorder events are published through the existing event publisher. Prometheus counters cover category/collection creation and deletion plus product assignments.

## Invariants

- Slugs are lower-case, ASCII-safe, trimmed, and hyphen-normalized.
- Names are whitespace-normalized and bounded.
- Sort/display order values cannot be negative.
- Product assignment requires a product in the same store.
- Optimistic versions prevent lost updates.

Collections expose a forward-compatible type registry (`manual`, `smart`,
`seasonal`, `featured`); only manual behavior is implemented. Reserved route
slugs such as `admin`, `api`, `search`, `new`, `sale`, and `default` are
rejected. Materialized category paths/depth are intentionally deferred until
hierarchy read patterns require them; cycle protection is already enforced.

## Verification

Run Black, Ruff, MyPy, Alembic upgrade/check, and the complete pytest suite from `backend/`. Docker validation remains subject to local daemon availability.
