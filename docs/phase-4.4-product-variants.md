# Phase 4.4 — Product Variants

Status: implemented, pending review

## Scope

Variants are store-owned records nested under a Product. They provide a stable
store-wide reference and a temporary canonical JSONB attribute map such as `size: M` and
`color: Navy`. Pricing, inventory quantities, reservations, and public product
read models remain outside this phase.

## Invariants

- every repository query proves Product ownership through its Store;
- a variant reference is unique among active records in one Store;
- a canonical SHA-256 attribute signature is unique among active variants of
  one Product, preventing duplicate size/color combinations;
- attributes contain 1–12 non-empty text key/value pairs and keys are compared
  case-insensitively;
- update and deletion use optimistic versions; deletion is a soft delete and
  disables the variant.

## API

- `POST /api/v1/products/{product_id}/variants`
- `GET /api/v1/products/{product_id}/variants`
- `PATCH /api/v1/products/{product_id}/variants/{variant_id}`
- `DELETE /api/v1/products/{product_id}/variants/{variant_id}?version=N`

The routes reuse `catalog:view` and `catalog:update` permissions. References,
attribute values, and signatures are not emitted to events or metrics. This MVP
does not emit variant domain events or transactional outbox records.

## Deferred completion

Phase 4.8 replaces the JSONB map with controlled, normalized attributes while
preserving these management APIs. It also adds safe variant domain events and
transactional outbox publication for Search, Analytics, cache invalidation,
Notifications, and future Inventory consumers. See
[ADR 0010](adr/0010-product-variant-mvp-deferral.md).

## Persistence

Migration `697a9e0d3c1b_create_product_variants.py` creates
`product_variants`, including foreign keys, indexes, partial unique indexes,
soft-delete, audit, and version columns.
