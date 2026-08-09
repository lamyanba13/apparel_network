# ADR 0023: Retailer Catalog Ingestion as an Orchestration Boundary

- Status: Accepted
- Date: 2026-08-09

## Context

Retailers may provide structured exports or rely on platform staff to collect
product, image, price, and stock data. Both paths must produce identical
marketplace records. A permanent imported-product model would duplicate catalog
ownership and cause pricing, inventory, media, and lifecycle rules to diverge.

## Decision

Create a temporary, Store-scoped Catalog Import boundary with explicit preview
and commit stages. Persist only job, normalized-row, structured-error, and staged
media metadata. Source adapters normalize input; they do not own marketplace
entities.

Commit only through the existing Product, Product Variant, Catalog Taxonomy,
Product Media, Pricing, and Inventory application services in one request-owned
transaction. Capture canonical identifiers and optimistic versions during
preview. A conflict during commit rolls back the complete canonical mutation.
Inventory changes use reconciliation and its established movement, Reservation,
locking, audit, event, and optimistic-version rules.

Use Store + SKU identities, request idempotency keys, Store-scoped spreadsheet
checksums, the shared Store owner/active-member predicate, existing object
storage, and the Phase 5.9 transactional outbox. Reject formulas, unsafe paths,
unsupported files, and ambiguous canonical matches.

## Consequences

- Online, POS-exported, staff-collected, and manually supplied products become
  the same canonical entities.
- Preview can report mixed row errors without partially mutating the catalog.
- Temporary ingestion storage adds lifecycle and cleanup responsibilities but
  does not become a PIM.
- Future POS/API connectors can be added before normalization without changing
  downstream domain ownership.
- Canonical service compatibility for accepted Store staff must consistently use
  the shared Store-access predicate.

