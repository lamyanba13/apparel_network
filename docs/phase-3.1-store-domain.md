# Phase 3.1 Store Domain

## Scope

Phase 3.1 introduces the Store bounded context after the Identity freeze. It
owns Store profiles, contact and address data, lifecycle state, persistence,
owner-scoped CRUD, domain events, and operational metrics.

This phase does not implement Store verification endpoints, Store staff,
catalog, products, inventory, reservations, search, analytics, notifications,
orders, payments, or media uploads. Logo and banner values are URL
placeholders only.

## Architectural boundary

The module is located at `backend/app/modules/stores/` and follows the
modular-monolith Clean Architecture layers:

```text
api
  -> application services and schemas
      -> domain models and events
      -> repository/event ports
infrastructure
  -> implements repository and event ports
  -> depends inward on application and domain contracts
```

Identity remains unchanged. The Store API consumes only the stable
`CurrentIdentity` principal and `require_permission` dependency. Persistence
stores the owner UUID through a database foreign key to `identity_users.id`;
the Store module does not import the Identity ORM model or repository.

## Aggregate and persistence model

`Store` is the aggregate root. `StoreAddress` and `StoreContact` are immutable
domain value objects embedded in the `stores` table.

| Concern | Persistence |
|---|---|
| Identity | UUIDv7 `id`; UUID `owner_id` |
| Profile | `name`, unique canonical `slug`, optional `description` |
| Contact | `phone`, normalized lowercase `email`, optional HTTP(S) `website` |
| Address | address line, city, district, state, country, postal code |
| Location | nullable latitude and longitude, supplied together |
| Media placeholders | nullable HTTP(S) `logo_url` and `banner_url` |
| Lifecycle | `status` and independent `verification_status` |
| Concurrency | positive monotonically increasing `version` |
| Retention | `created_at`, `updated_at`, nullable `deleted_at` |

The API never accepts an owner ID, slug, lifecycle state, verification state,
timestamps, or deletion state from a client. Owner identity comes from the
verified access token context. Slugs are generated server-side and stay stable
when the Store name changes.

## Status models

Operational Store status:

```text
draft -> pending_review -> active
   |           |             |
   +-----------+-------------+-> suspended
   +-----------+-------------+-> closed
```

Verification status is independent:

- `unverified`
- `pending`
- `verified`
- `rejected`

The application lifecycle service supports:

- submit: `draft` to `pending_review` and `pending`;
- verify: `pending_review` to `active` and `verified`;
- suspend: `pending_review` or `active` to `suspended`;
- close: any non-closed state to `closed` with soft deletion.

Phase 3.1 exposes no verification or administration lifecycle routes.
`StoreLifecycleService` is the internal foundation for Phase 3.2. Invalid or
racing transitions return a conflict and never silently overwrite state.

## Application services

- `StoreService` orchestrates owner-scoped create, list, read, update, and
  close operations.
- `StoreValidationService` normalizes text and email and validates phone,
  URLs, postal code, and coordinates.
- `StoreSlugService` creates canonical ASCII URL slugs and a UUIDv7-derived
  suffix for an observed collision.
- `StoreLifecycleService` performs atomic state transitions separately from
  HTTP transport.

Repositories flush changes but never commit. The API dependency is the
transaction boundary: it commits after successful request processing and
rolls back on failure.

## API contract

All endpoints require an authenticated principal and a database-resolved
permission. There are no role-name comparisons.

| Method and path | Permission | Outcome |
|---|---|---|
| `POST /api/v1/stores` | `store:create` | Create a draft Store owned by the current identity. |
| `GET /api/v1/stores` | `store:view` | List the current identity's non-deleted Stores with bounded offset pagination. |
| `GET /api/v1/stores/{store_id}` | `store:view` | Read an owned, non-deleted Store. |
| `PATCH /api/v1/stores/{store_id}` | `store:update` | Update owner-editable fields using an expected version. |
| `DELETE /api/v1/stores/{store_id}` | `store:delete` | Close and soft-delete an owned Store. |

Cross-owner and missing resources use the same `404` response to avoid
disclosure. Stale versions and invalid lifecycle transitions use `409`.
Validation errors use the platform RFC 9457 problem format. OpenAPI documents
Bearer security, explicit response models, error responses, and
`x-authorization` requirements.

## Events

The typed event contract contains UUIDv7 event ID, timestamp, optional
correlation ID, Store ID, owner ID, and only state metadata required by the
event:

- `StoreCreated`
- `StoreUpdated`
- `StoreSubmitted`
- `StoreVerified`
- `StoreSuspended`
- `StoreClosed`

The initial in-process publisher writes structured, allowlisted audit logs.
It never logs Store contact data, address data, access tokens, or credentials.
The common event port permits a future transactional outbox without changing
domain or application services.

## Metrics

The shared Prometheus registry exposes unlabeled, low-cardinality metrics:

- `fashion_network_stores_created_total`
- `fashion_network_stores_active_total`
- `fashion_network_stores_verified_total`

Active and verified gauges are refreshed from PostgreSQL after aggregate
creation, deletion, and lifecycle changes. Metrics do not contain Store IDs,
owner IDs, names, slugs, emails, or locations.

## Migration

Alembic revision `d48004d70e46` follows Identity head `c3d91e7a4b62`.
It creates only `stores` and is fully reversible.

Explicit indexes:

- `ix_stores_owner_id_status` supports owner-scoped listings;
- `ix_stores_status_verification` supports operational state queries;
- partial `ix_stores_active_public` supports future verified/public
  projection work while excluding deleted and non-active rows.

Database enforcement includes the owner foreign key, unique slug, canonical
slug, field length, coordinate completeness/range, and positive-version
constraints.

## Verification

Phase 3.1 tests cover:

- UUIDv7 creation and repository persistence;
- create, owner-scoped list/read, optimistic update, and soft delete;
- slug generation and collision handling;
- input normalization and invalid contact/location rejection;
- database uniqueness, checks, foreign key, and explicit indexes;
- lifecycle transitions and conflict behavior;
- all six event contracts;
- Store Prometheus exposition;
- OpenAPI paths, schemas, Bearer security, and permissions;
- authorization through the permission service with no role comparison;
- Alembic upgrade, downgrade, linear head, and metadata drift.

## Phase 3.2 boundary

Store Verification may add reviewed submission and administrative verification
workflows, verification evidence, rejection reasons, and corresponding
authorization policy. It must reuse the lifecycle service and existing
Identity interfaces. Store staff, catalog, inventory, media upload, search,
analytics, and all commerce behavior remain out of scope until their approved
phases.
