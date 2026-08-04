# Backend foundation

Phase 4.3 includes isolated Product Media persistence, validation, storage
compensation, and owner-scoped `/api/v1/products/{product_id}/media` routes.

The backend is a Python 3.13 FastAPI modular monolith managed by Poetry.

The frozen `foundation-v1` baseline provides the production operations
foundation:

- SQLAlchemy 2.x typed declarative metadata;
- asyncpg engine and bounded connection pool;
- request-scoped `AsyncSession` dependency;
- rollback on failed request work and automatic session cleanup;
- lifespan startup validation and graceful pool disposal;
- process-only `GET /health/live`;
- dependency-aware `GET /health/ready` for PostgreSQL, RabbitMQ, Redis,
  Meilisearch, and MinIO/R2;
- startup-sequence `GET /health/startup`;
- Alembic autogeneration wiring and the reviewed Phase 2.1 Identity revision;
- reusable UUIDv7, timestamp, selective soft-delete, audit, and optimistic
  version mixins.
- request-scoped IDs, correlation, start time, client IP, user agent, and a
  deliberately empty authenticated-user placeholder;
- development-pretty and production-JSON structured logging;
- centralized RFC 9457-style validation, HTTP, database, and unexpected-error
  translation;
- CORS, trusted-host, GZip, timing, request logging, and environment-aware
  security-header middleware;
- bounded cursor/offset pagination, allowlisted sorting/filtering primitives,
  response models, validators, common types, and narrowly named utilities;
- an empty `/api/v1` router plus customized development OpenAPI;
- Prometheus HTTP, status, latency, dependency, query, database-pool, and
  worker-placeholder metrics at private `GET /metrics`;
- environment-controlled OpenTelemetry instrumentation for FastAPI,
  SQLAlchemy, HTTPX, and Celery/RabbitMQ;
- disabled-by-default, PII-scrubbed Sentry for unhandled API, startup, and
  worker failures;
- slow request/query and startup/shutdown timing diagnostics;
- an injected, disabled-by-default rate-limiter port with public/store/admin
  policy scopes;
- validated idempotency keys, canonical request fingerprints, and a future
  authoritative storage port;
- opt-in ETag conditional requests and endpoint deprecation/sunset helpers;
- Brotli response compression with standards-aware GZip fallback.

Phase 2.1 added the Identity persistence records, schemas, repository
ports/adapters, and initial migration.

Phase 2.2 adds authentication only: Argon2id password verification, 15-minute
Ed25519 access JWTs, opaque hashed refresh credentials, rotation/reuse
detection, session revocation, and `/api/v1/auth` login, refresh, logout, and
logout-all routes. It does not add authorization or business-module behavior.

Phase 2.3 adds owner-scoped session lifecycle management. Phase 2.4 adds
database-driven RBAC resolution and reusable authorization policies. Phase 2.5
adds account password maintenance, opaque-token recovery and email
verification, progressive expiring lockouts, and bounded cleanup. It does not
add MFA, external identity providers, notification providers, or business
modules.

Phase 2.6 freezes the reviewed Identity module. Its architecture, security and
operational invariants, public API contract, and production verification gates
are recorded in
[`docs/phase-2.6-identity-freeze.md`](../docs/phase-2.6-identity-freeze.md).
Phase 3 modules may consume Identity ports and principal context but must not
place business ownership rules inside Identity.

Phase 3.1 adds the separate Store bounded context: owner-scoped Store profile
CRUD, lifecycle foundations, persistence, typed events, metrics, and a reviewed
Alembic migration. Verification workflows, staff, catalog, inventory, media,
search, reservations, and commerce behavior remain outside this phase. See
[`docs/phase-3.1-store-domain.md`](../docs/phase-3.1-store-domain.md).

Phase 3.2 adds Store verification submission, administrative review,
approval/rejection, reopening, private evidence metadata, atomic Store-state
synchronization, audit events, and metrics. It changes no Identity behavior or
Phase 3.1 CRUD contract. See
[`docs/phase-3.2-store-verification.md`](../docs/phase-3.2-store-verification.md).

Phase 3.3 adds Store-local memberships, bounded invitations, invitee
acceptance/decline, suspension/reactivation, removal, database-enforced
uniqueness, typed events, and metrics. It consumes frozen Identity interfaces
without adding role comparisons or changing authentication and authorization.
See
[`docs/phase-3.3-store-staff-management.md`](../docs/phase-3.3-store-staff-management.md).

Phase 3.4 adds Store-only logo, banner, and gallery images with decoded-content
validation, owner-scoped APIs, private MinIO/R2 storage, compensated object
mutations, PostgreSQL metadata, typed events, and low-cardinality metrics. See
[`docs/phase-3.4-store-media.md`](../docs/phase-3.4-store-media.md).

From this directory:

```text
poetry install
poetry run alembic upgrade head
poetry run alembic check
poetry run uvicorn app.main:app --reload
```

The normal repository workflow runs these commands through Docker Compose; see
the root `README.md`.

Phase 4.0 adds the Store-owned Catalog bounded context. Catalog metadata is
persisted in PostgreSQL with scoped ownership, lifecycle validation, soft
deletion, optimistic locking, safe events, and catalog permissions. Products,
variants, pricing, and inventory are intentionally not implemented. See
[`docs/phase-4.0-catalog-foundation.md`](../docs/phase-4.0-catalog-foundation.md).

Phase 4.1 adds Product persistence and owner-scoped CRUD beneath Catalogs.
Variants, inventory, pricing, product media, and reservations remain excluded.
See [`docs/phase-4.1-product-foundation.md`](../docs/phase-4.1-product-foundation.md).

Phase 4.5 adds the Inventory Foundation beneath Product Variants. PostgreSQL
enforces one inventory record per variant and the non-negative derived quantity
invariant; repositories flush only and request dependencies own commits and
rollbacks. See
[`docs/phase-4.5-inventory-foundation.md`](../docs/phase-4.5-inventory-foundation.md).

Phase 4.6 introduces Product Pricing as an independent bounded context. Pricing
owns fixed-precision commercial amounts, currency and effective-period validation,
lifecycle, optimistic locking, soft deletion, events, metrics, and owner-scoped
HTTP persistence. See
[`docs/phase-4.6-product-pricing.md`](../docs/phase-4.6-product-pricing.md).

Phase 4.7 extends Pricing with Price Lists, explicit ISO-4217 currencies,
effective schedules, customer groups, assignments, and the production-backed
resolver at `/api/v1/pricing/resolve`. It performs no conversion or promotion
logic. See
[`docs/phase-4.7-price-lists-and-multi-currency.md`](../docs/phase-4.7-price-lists-and-multi-currency.md).

Phase 4.8 normalizes Product Variant attributes into controlled Store-owned
definitions, values, and Variant assignments while preserving the existing
Variant API shape. Variant mutations persist identifier-only events to the
transactional `event_outbox` in the same request transaction; no publisher is
introduced. See
[`docs/phase-4.8-variant-attribute-normalization.md`](../docs/phase-4.8-variant-attribute-normalization.md).

Phase 5.0 introduces the customer-owned Shopping Cart bounded context. Cart Item
mutations resolve production Pricing and validate production Inventory while
persisting stable commercial snapshots; Inventory is never reserved. Cart writes
and identifier-only events share the request transaction. See
[`docs/phase-5.0-shopping-cart-foundation.md`](../docs/phase-5.0-shopping-cart-foundation.md).

Phase 5.1 introduces Checkout Sessions as an immutable boundary between mutable
Carts and future Orders. Checkout re-resolves Pricing, revalidates Inventory,
freezes Item snapshots, and confirms the source Cart transactionally without
reserving stock or creating Orders or Payments. See
[`docs/phase-5.1-checkout-foundation.md`](../docs/phase-5.1-checkout-foundation.md).
