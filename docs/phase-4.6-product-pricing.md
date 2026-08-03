# Phase 4.6 — Product Pricing Foundation

Status: implemented; validation complete; pending approval

Product Pricing is a separate bounded context from Product. Products retain
descriptive catalog information; Pricing owns commercial amounts, currency,
effective periods, lifecycle, optimistic concurrency, audit attribution, and
soft deletion. This boundary permits promotions, coupons, regional and
customer-group pricing, scheduled prices, multiple currencies, and flash sales
to be added without moving price fields into Product.

## Architecture

The module follows the repository's Domain, Application, Infrastructure, API,
Persistence, Events, Metrics, Tests, and Documentation layers. Repositories are
owner-scoped and flush without committing. FastAPI request dependencies own commit
and rollback behavior. Pricing validates ownership across Store, Catalog, Product,
and optional Product Variant boundaries without importing another module's
repository implementation into its application layer.

## Persistence

`product_prices` stores UUIDv7 identifiers, Store/Product/optional Variant keys,
ISO-style three-letter currency codes, fixed-precision decimal amounts, tax class,
effective bounds, lifecycle status, optimistic version, timestamps, actor audit
fields, and deletion attribution. PostgreSQL enforces non-negative amounts,
sale/base and compare-at/base relationships, valid effective periods, archived
soft deletes, foreign keys, lookup indexes, and one active Variant/currency/period
record with null effective bounds treated consistently.

## Lifecycle

Prices are created as `draft`, may transition to `active`, and may then transition
to `archived`. Active prices cannot return to draft, and archived prices cannot be
reactivated. DELETE archives and soft-deletes the record. PATCH and DELETE require
the current version; stale writes return `409 Conflict` while missing or cross-Store
resources return `404 Not Found`.

## API and authorization

The authenticated API exposes POST and GET collection operations plus GET, PATCH,
and DELETE item operations at `/api/v1/prices`. Collection filters support Store,
Product, Variant, currency, status, effective timestamp, offset, and limit.
Authorization uses `price:create`, `price:view`, and `price:update`; the migration
grants the appropriate permissions to super administrators, Store owners, and
Store staff.

## Events and metrics

Identifier-only events are `ProductPriceCreated`, `ProductPriceUpdated`,
`ProductPriceActivated`, `ProductPriceArchived`, and `ProductPriceDeleted`. Payloads
contain only Price, Product, optional Variant, Store, version, and timestamp data.
Low-cardinality counters record created, updated, deleted, and activated prices.

## Scope boundary

This foundation does not implement promotions, coupons, region/customer-group
selection, automatic scheduling jobs, tax calculation, flash-sale orchestration,
or checkout totals. It establishes the schema and module boundary those features
will extend.
