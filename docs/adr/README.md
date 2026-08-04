# Architecture Decision Records

Architecture Decision Records (ADRs) preserve the reasoning behind foundational technical choices. They complement the normative architecture documents; they do not replace them.

## Lifecycle

- `Proposed`: under review and not yet binding.
- `Accepted`: approved and part of the architecture baseline.
- `Deprecated`: retained for history but no longer recommended.
- `Superseded`: replaced by a later ADR, which must be linked from both records.

Accepted ADRs are immutable historical records. A material change is documented in a new ADR that supersedes the prior decision.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith | Accepted |
| [0002](0002-rabbitmq-over-redis.md) | RabbitMQ as the Celery broker | Accepted |
| [0003](0003-postgresql.md) | PostgreSQL as the system of record | Accepted |
| [0004](0004-fastapi.md) | FastAPI for the backend | Accepted |
| [0005](0005-meilisearch.md) | Meilisearch for search projections | Accepted |
| [0006](0006-minio.md) | MinIO for local object-storage development | Accepted |
| [0007](0007-opentelemetry.md) | OpenTelemetry for distributed telemetry | Accepted |
| [0008](0008-observability.md) | Layered observability strategy | Accepted |
| [0009](0009-identity-access-and-refresh-tokens.md) | Identity access and refresh token architecture | Accepted |
| [0010](0010-product-variant-mvp-deferral.md) | Product Variant MVP deferral | Accepted; fulfilled in Phase 4.8 |
| [0011](0011-pricing-resolution-algorithm.md) | Pricing resolution algorithm | Accepted |
| [0012](0012-shopping-cart-design.md) | Shopping Cart design | Accepted |
| [0013](0013-checkout-boundary.md) | Checkout boundary | Accepted |
| [0014](0014-order-boundary.md) | Order boundary | Accepted |
| [0015](0015-payment-boundary.md) | Payment boundary | Accepted |
| [0016](0016-inventory-reservation-boundary.md) | Inventory Reservation boundary | Accepted |
| [0017](0017-shipment-boundary.md) | Shipment and Fulfillment boundary | Accepted |
| [0018](0018-return-refund-boundary.md) | Return and Refund boundary | Accepted |

The implementation conformance review and frozen Identity invariants are
recorded in the [Phase 2.6 Identity Module Freeze](../phase-2.6-identity-freeze.md).
That review does not supersede or modify an accepted ADR.
