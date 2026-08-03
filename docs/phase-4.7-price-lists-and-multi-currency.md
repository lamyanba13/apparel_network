# Phase 4.7 — Price Lists & Multi-Currency

Status: implemented; validation pending final approval

Phase 4.7 extends the Pricing bounded context with Store-owned Price Lists,
explicit multi-currency selection, scheduled availability, customer-group
targeting, price assignments, and deterministic price resolution. It does not
perform currency conversion and does not implement promotions, campaigns,
coupons, or exchange-rate synchronization.

## Architecture

The implementation retains the Domain, Application, Infrastructure,
Persistence, API, Events, Metrics, Tests, and Documentation boundaries.
Repositories flush only; FastAPI dependencies own commit and rollback. All
management and resolution paths validate Store ownership and return `404 Not
Found` for cross-Store resources.

The Price List layer reuses Phase 4.6 `ProductPrice` records. An assignment links
a Product Price to a Price List without copying amounts or commercial metadata.
Unassigned Phase 4.6 prices remain the backward-compatible default-Store
fallback.

## Persistence

`price_lists` stores UUIDv7 identity, Store ownership, canonical slug, explicit
ISO-4217 currency, non-negative priority, lifecycle, customer group, effective
bounds, default-list flag, optimistic version, timestamps, actor attribution,
and soft-deletion metadata. PostgreSQL enforces:

- unique `(store_id, slug)`;
- at most one non-deleted default list per Store and currency;
- default lists are active and public;
- valid effective periods and non-negative priorities;
- archived soft deletes and positive versions;
- indexes for Store, currency, priority, status, and effective bounds.

`price_list_assignments` stores a UUIDv7 identity, Price List and Product Price
foreign keys, optimistic version, creation timestamp, and actor attribution. A
Price can be assigned to a given Price List only once.

No resolution cache is persisted in this phase. PostgreSQL remains authoritative,
and the optional cache table is deferred until measurement demonstrates a need.

## Lifecycle and concurrency

Price Lists are created as `draft`, transition to `active`, and may transition to
`archived`. Active lists cannot return to draft, and archived lists cannot be
reactivated. DELETE archives and soft-deletes the list. PATCH and DELETE require
the current version; stale versions return `409 Conflict`.

Assignments can be prepared while a list is draft, but the resolver considers
only active lists and active prices. Unassignment removes only the association;
it does not delete either record.

## Multi-currency and scheduling

Currency codes are normalized to uppercase and validated against the active
ISO-4217 code set. Every requested currency requires an explicit Product Price
in that currency. No automatic conversion or rate lookup occurs.

Both the Product Price and Price List effective periods use an inclusive start
and exclusive end: `effective_from <= timestamp < effective_until`. Null bounds
are open-ended. Inactive, archived, deleted, future, and expired records are
ignored.

## Customer groups

Supported groups are `public`, `wholesale`, `vip`, `staff`, and `custom`. Public
requests consider public lists only. A non-public request first considers its
exact group, then public lists as a fallback. Within that group tier, normal
priority and deterministic tie-breaking apply. `custom` is a foundation marker;
custom-group identifiers and membership synchronization remain future work.

## Resolution algorithm

The resolver accepts Store, Product, optional Variant, currency, customer group,
and timezone-aware timestamp. It evaluates:

1. eligible assigned Variant-specific prices;
2. eligible assigned Product-level prices;
3. eligible unassigned Phase 4.6 prices as the default-Store fallback.

Within an assigned specificity level, exact customer-group matches precede the
public fallback. The highest Price List priority wins. Ties select the newest
`effective_from` (open-start values sort last), followed by the lowest Price List
UUID. The fallback uses Variant before Product, then newest price effective start
and lowest Price UUID. The selected sale price is returned when present;
otherwise the base price is returned.

See [ADR 0011](adr/0011-pricing-resolution-algorithm.md) for the decision record.

## API and authorization

Price List management is exposed at `/api/v1/price-lists`, assignments at
`/api/v1/price-lists/{id}/prices`, and resolution at
`GET /api/v1/pricing/resolve`. OpenAPI includes all filters, response schemas,
Bearer security, and authorization metadata.

Permissions are `price:list:create`, `price:list:view`, `price:list:update`, and
`price:resolve`. The authorization vocabulary remains database-driven and now
supports colon-delimited resource namespaces while preserving all existing
two-segment permissions.

## Events and metrics

Identifier-only events are `PriceListCreated`, `PriceListUpdated`,
`PriceListArchived`, `PriceAssigned`, `PriceUnassigned`, and `PriceResolved`.
Payloads contain Price List ID, Price ID when applicable, Store ID, version, and
timestamp only.

Low-cardinality telemetry includes:

- `fashion_network_price_list_created_total`;
- `fashion_network_price_list_updated_total`;
- `fashion_network_price_assigned_total`;
- `fashion_network_price_resolved_total`;
- `fashion_network_price_resolution_duration_seconds`.

## Scope boundary

Promotions, discounts, coupons, campaign eligibility, tax calculation, automatic
currency conversion, rate synchronization, and customer-group membership
management are intentionally excluded.
