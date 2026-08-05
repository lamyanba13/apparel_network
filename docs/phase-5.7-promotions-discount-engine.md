# Phase 5.7 — Promotions & Discount Engine

## Status

Implemented and approved on 2026-08-05 after the complete validation matrix
passed.

## Boundary

Promotions is a Store-scoped bounded context that owns Promotion definitions,
typed eligibility Rules, Coupons, immutable Redemption snapshots, customer usage,
deterministic stacking, optimistic versions, identifier-only events, and metrics.

It never rewrites Product Prices, Price Lists, Cart Item price snapshots, Checkout
Items, or Order Items. Pricing remains authoritative upstream. Promotions operate
on production Cart summaries after price resolution and before Checkout totals.

## Promotion lifecycle

```text
DRAFT -> ACTIVE -> ARCHIVED
```

Only drafts activate. Active or draft Promotions may archive. Archived and
soft-deleted Promotions cannot reactivate or be modified. All mutations require
the current optimistic version and stale requests return `409 Conflict`.

## Promotion types

The engine supports percentage, fixed amount, buy-X-get-Y, bundle, tier discount,
and free-shipping Promotions. Amounts preserve the Cart currency and use four
decimal places. Per-Promotion maximum discounts and the Cart subtotal cap prevent
negative final totals.

Free shipping records an eligible zero-value commercial line in this phase. The
future shipping-rate boundary may interpret it; Promotions does not write Shipment
or carrier data.

## Conditions and eligibility

Rules can restrict eligible Cart Items by Catalog, Category, Brand, Product, and
Variant. Store and currency are mandatory evaluation boundaries. Promotion-level
conditions support customer group, first purchase, public or coupon-only access,
minimum subtotal, minimum quantity, total usage, per-customer usage, effective
period, maximum discount, and maximum stack.

Evaluation loads immutable Cart price snapshots and product classification
context. It does not duplicate Pricing calculations or mutate persistence.

## Coupons

Coupon codes are normalized to uppercase and unique within a Store. Coupons have
independent activation, effective periods, total usage, per-customer usage,
optimistic versions, and soft deletion. Invalid, inactive, expired, or exhausted
codes are returned as rejected evaluation results without exposing another Store.

## Deterministic resolution

The resolver performs the following stable sequence:

1. Load active, effective Promotions for the Cart Store.
2. Normalize and validate Coupon codes.
3. Validate customer group, first purchase, currency, dates, and usage limits.
4. Match Rules against Cart Item Product context.
5. Enforce minimum subtotal and eligible quantity.
6. Calculate each Promotion type from resolved Cart prices.
7. Sort by descending priority and stable Promotion identifier.
8. Select the highest-priority exclusive Promotion, or apply stackability and the
   strictest maximum-stack limit.
9. Cap individual lines against the remaining subtotal so the immutable breakdown
   exactly equals the discount total.

Higher priority always wins. Exclusive Promotions prevent all stacking.

## Cart, Checkout, and Order integration

Cart summaries optionally evaluate public Promotions and supplied Coupons without
changing stored Cart or Cart Item snapshots.

Checkout creation evaluates once and persists one immutable Redemption snapshot
per applied Promotion. Coupon and customer usage advances in that same request
transaction. Checkout summaries expose subtotal, discount total, final total, and
the frozen lines.

Order creation links those exact Checkout-owned Redemption snapshots to the new
Order without recalculation. Order summaries expose the same identifiers, coupon
code snapshots, amounts, currency, and resolution metadata.

## HTTP API

- `POST /api/v1/promotions`
- `GET /api/v1/promotions`
- `GET /api/v1/promotions/{promotion_id}`
- `PATCH /api/v1/promotions/{promotion_id}`
- `DELETE /api/v1/promotions/{promotion_id}`
- `POST /api/v1/promotions/{promotion_id}/activate`
- `POST /api/v1/promotions/{promotion_id}/archive`
- `POST /api/v1/coupons`
- `GET /api/v1/coupons`
- `PATCH /api/v1/coupons/{coupon_id}`
- `DELETE /api/v1/coupons/{coupon_id}`
- `POST /api/v1/promotions/evaluate`

Every route declares its permission in OpenAPI. Store-owned management resources
use `404` concealment across ownership boundaries. Customer evaluation uses the
owned Cart boundary and also returns `404` for cross-user access.

## Events and metrics

Promotion lifecycle, Coupon creation/redemption, and application/removal events
are written transactionally using identifier-only payloads. Discount amounts and
Coupon codes never enter event payloads.

Low-cardinality counters cover Promotion creation and activation, Coupon
redemption, Promotion application, and discount amount by normalized currency. An
unlabeled histogram measures resolution duration.

## Verification

The production-backed integration test traverses authentication, authorization,
Store, Product, Variant, Inventory, Pricing, Cart, Promotions, Checkout, Order,
PostgreSQL, the transactional outbox, and Prometheus metrics. It uses no mocks,
fake repositories, or direct ORM insertion.
