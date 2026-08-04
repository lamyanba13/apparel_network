# ADR 0010: Product Variant MVP Deferral

- Date: 2026-08-02
- Status: Accepted (deferral fulfilled by Phase 4.8)

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

Phase 4.8 introduces `product_attributes`, `product_attribute_values`, and
`product_variant_attribute_values`. It backfills the existing map without
breaking the Phase 4.4 API, retains duplicate-combination protection, and
rejects unmapped attributes before public publication depends on them.

Phase 4.8 also writes safe `VariantCreated`, `VariantUpdated`,
`VariantDeleted`, `VariantAttributeAssigned`, `VariantAttributeRemoved`, and
`VariantArchived` events to `event_outbox` in the same database transaction as
each Variant write. Direct publication is deferred; future consumers must be
idempotent and tolerate replay.

## Consequences

- Phase 4.4 can support private catalog management sooner.
- JSONB attributes cannot become a query, search, facet, or localization
  contract.
- The temporary JSONB exception is complete: Variant persistence now uses
  controlled normalized values and the JSONB column has been removed.
- The Phase 4.4 management API remains compatible while its inputs resolve to
  normalized values.
- Projection consumers remain deferred until the outbox dispatcher is
  implemented.
