# ADR 0010: Product Variant MVP Deferral

- Date: 2026-08-02
- Status: Proposed

## Context

Phase 4.4 introduces Product Variant management before the controlled attribute
taxonomy, public faceting, and projection consumers are ready. A normalized
attribute model is required for reusable validation, filtering, search facets,
localization, and administrator management. Variant changes also need safe
domain events and transactional outbox records before Search, Analytics,
Inventory, cache invalidation, or Notifications consume them.

## Decision

Phase 4.4 stores a canonical JSONB `attributes` map and SHA-256 signature on
each variant as a temporary, management-only representation. It remains outside
public filtering, faceting, localization, and publication eligibility.

Phase 4.8 will introduce `attribute_definitions`, `attribute_values`, and
`product_variant_attribute_values`. It will backfill the existing map without
breaking the Phase 4.4 API, retain duplicate-combination protection, and reject
unmapped attributes before public publication depends on them.

Phase 4.8 will also emit safe `ProductVariantCreated`,
`ProductVariantUpdated`, and `ProductVariantDeleted` events through a
transactional outbox in the same database transaction as each variant write.
Consumers must be idempotent and tolerate replay.

## Consequences

- Phase 4.4 can support private catalog management sooner.
- JSONB attributes cannot become a query, search, facet, or localization
  contract.
- Phase 4.8 is required before variants support public publication, controlled
  attributes, or projection consumers.
- Technical-owner approval is required before this proposed exception becomes
  binding.
