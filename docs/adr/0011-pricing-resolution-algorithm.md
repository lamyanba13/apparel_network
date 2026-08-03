# ADR 0011: Pricing Resolution Algorithm

- Status: Accepted
- Date: 2026-08-03

## Context

Phase 4.7 introduces multiple Price Lists, currencies, effective periods, and
customer groups. Resolution must be deterministic, tenant-safe, compatible with
Phase 4.6 Product Prices, and independent of promotions or exchange rates.

## Decision

Pricing resolution is a PostgreSQL-authoritative application service. It filters
to the requested Store, Product, currency, timestamp, active lifecycle, and
non-deleted records before ordering candidates.

Assigned Variant prices precede assigned Product prices. Exact non-public
customer groups precede the public fallback. Within a specificity and group tier,
higher Price List priority wins, then newer `effective_from`, then lower Price
List UUID. If no assigned candidate exists, an eligible unassigned Phase 4.6
price is returned as the default-Store fallback, preferring Variant over Product.

Currency conversion is never implicit. A request succeeds only when an explicit
price exists in the requested ISO-4217 currency. Effective starts are inclusive
and effective ends are exclusive.

## Consequences

- Resolution is deterministic across application instances.
- Existing unassigned Product Prices remain usable.
- Customer-specific pricing can safely fall back to public pricing.
- Price List priority is meaningful only after specificity and group matching.
- No exchange-rate, promotion, or coupon behavior enters the resolver.
- The optional resolution cache can be added later without changing the contract.
