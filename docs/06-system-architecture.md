# System Architecture

## Architectural style

Fashion Network is a feature-oriented modular monolith following Clean Architecture and SOLID principles. All backend modules share one codebase, runtime release, and PostgreSQL database, but communicate through explicit public interfaces and application events.

This provides:

- atomic transactions for inventory and reservations;
- simple deployment and debugging;
- independently understandable feature modules;
- a path to scale API and worker processes horizontally;
- clear seams for future change without committing to microservices.

The architecture is not a layered monolith where every feature imports every shared model. Each module contains its own domain, application, infrastructure, and presentation concerns.

## System context

```text
Customers ───────> Public Next.js frontend ──┐
                                             │ HTTPS / JSON API
Store staff ─────> Dashboard Next.js app ────┼──> FastAPI modular monolith
Administrators ──> Dashboard Next.js app ────┘          │
                                                        ├── PostgreSQL (authoritative)
                                                        ├── Redis (ephemeral cache/rate limits)
                                                        ├── RabbitMQ (Celery broker)
                                                        ├── Meilisearch (search projection)
                                                        ├── Cloudflare R2 (media)
                                                        ├── Celery workers / scheduler
                                                        ├── Notification provider(s)
                                                        ├── Sentry
                                                        └── PostHog
```

Browsers never connect directly to PostgreSQL, Redis, or Meilisearch. Direct-to-R2 upload is allowed only through short-lived authorization produced by the backend.

## Deployable units

| Unit | Responsibility | Scaling characteristic |
|---|---|---|
| Public frontend | Discovery, public details, customer account and reservations. | Scale by request volume; cache only explicitly public responses. |
| Dashboard | Store and admin workflows. | Scale independently; authenticated content is private by default. |
| Backend API | Synchronous application use cases and API contracts. | Stateless horizontal replicas. |
| Celery worker | Asynchronous application use cases. | Scale by queue depth and workload class. |
| Celery scheduler | Recurring task dispatch. | Single active scheduler or leader-safe equivalent. |
| Outbox dispatcher | Claims committed outbox records and publishes durable Celery work. | Scale with database-safe claiming; publisher confirms do not replace consumer idempotency. |

They are built and deployed from the same monorepo but need not be released simultaneously unless a contract or migration requires coordination.

## Clean Architecture dependency rule

Within each backend module:

```text
presentation/API ──> application ──> domain
infrastructure ─────> application/domain interfaces
bootstrap ──────────> all layers for dependency wiring only
```

- **Domain:** entities, value objects, policies, state machines, domain errors, and domain events. It imports neither FastAPI nor SQLAlchemy.
- **Application:** use cases/services, commands/queries, DTOs, ports, repository interfaces, transaction coordination, and authorization intent.
- **Infrastructure:** SQLAlchemy mappings and repositories, Meilisearch/R2/provider adapters, Celery transport adapters, and external integration details.
- **Presentation:** FastAPI routers, request/response schemas, dependency extraction, and translation between HTTP and application DTOs.

Dependencies point inward. Infrastructure implements ports declared inward. Framework objects do not enter the domain.

## Module ownership

| Module | Owns | Does not own |
|---|---|---|
| Auth | Credentials, sessions/tokens, verification and recovery, authentication policy. | User profile, store membership, admin business permissions. |
| Users | User profile, lifecycle/privacy request, global user status. | Credentials and store-specific roles. |
| Stores | Store profile, physical address, status, memberships and store permissions. | Product/inventory records. |
| Products | Product, variant, taxonomy references, publication state, product-media associations. | Stock quantities and storage transport. |
| Inventory | Store/variant stock, holds, movement ledger, availability policy. | Reservation customer workflow or product description. |
| Reservations | Reservation aggregate, expiry, customer/store workflow, references. | Exact stock mutation rules, which it invokes through Inventory's public service. |
| Search | Search document schema, indexing, query translation, ranking configuration, rebuilds. | Authoritative product/inventory truth. |
| Notifications | Notification records, templates, preferences, delivery attempts/adapters. | Deciding business state changes. |
| Admin | Administrative use cases, moderation queues, policy administration, and composition of the Audit module's permission-scoped query port. | Audit record ownership or direct bypass of module invariants. |
| Audit | Append-only audit event capture, integrity export, retention, and permission-scoped query port. | Product analytics, ordinary logs, or authorization decisions. |
| Analytics | Tracking plan integration, governed aggregates, store/platform reporting queries. | Audit/security logs and source business state. |
| Uploads | Upload authorization, object metadata, verification, cleanup, storage adapter. | Product publication and product-media ordering. |

### Shared kernel

The shared kernel MUST remain small:

- base identifier and UTC clock abstractions;
- common domain error primitives;
- transaction/event interfaces;
- pagination and correlation types;
- audit actor context;
- foundational authorization types.

Shared code MUST NOT contain feature entities, generic business services, or a global dumping-ground of utilities.

## Inter-module communication

Use these mechanisms in order:

1. A module's explicit application facade/port for synchronous behavior requiring an immediate answer.
2. Application/domain events for side effects that may occur after commit.
3. Read models specifically designed for cross-module query needs.

Modules MUST NOT import another module's SQLAlchemy models or query its tables directly from ordinary repositories.

Examples:

- Reservations calls the Inventory application facade to atomically acquire or release a hold.
- Product or inventory changes emit an outbox event consumed by Search.
- Reservation state changes emit events consumed by Notifications and Analytics.
- Admin invokes a module's administrative application interface; it does not update its tables directly.

Circular module dependencies are prohibited. Resolve them by clarifying ownership, introducing an inward port, or using an event.

## Transaction and event design

### Synchronous transaction

An application service:

1. validates caller intent and permissions;
2. loads aggregates through repositories;
3. applies domain rules;
4. persists changes inside one PostgreSQL transaction;
5. appends resulting integration events to an outbox in the same transaction;
6. commits;
7. returns an application DTO.

External network calls MUST NOT occur while holding inventory row locks or inside a database transaction unless strictly required and documented.

### Transactional outbox

The backend MUST use a transactional outbox for business events that drive search, notifications, or other critical asynchronous projections. A database-safe dispatcher publishes committed work through RabbitMQ with publisher confirms. Delivery is at least once; consumers deduplicate using event ID and consumer identity. Critical recurring outcomes such as expiry and projection integrity also have PostgreSQL reconciliation sweeps, so a broker acknowledgement gap cannot permanently lose the business effect.

Each event contains:

- globally unique event ID;
- stable event name and schema version;
- occurrence time in UTC;
- correlation and causation IDs;
- owning aggregate type and opaque identifier;
- minimal payload required by the consumer;
- no secrets and minimal personal data.

Events are contracts. Breaking changes require a new schema version and a coexistence/migration plan.

## Core data model

This is a logical model; exact names are finalized during schema design.

### Relational conventions

- Application-generated UUIDv7 values are the default primary and public identifiers because they are globally unique and more index-local than random UUIDv4. Security never depends on identifier secrecy.
- Every mutable aggregate has `created_at`, `updated_at`, and a monotonic `version` column. Timestamps are timezone-aware UTC and database-populated/validated.
- Append-only records have `occurred_at`/`created_at` and no `updated_at` unless their delivery metadata is a separately mutable record.
- Lifecycle state replaces blanket soft deletion. `deleted_at` is added only where an approved reversible deletion workflow actually exists.
- Foreign keys are explicit. Tenant-owned child tables carry `store_id` where it makes authorization/query scoping safer and use composite constraints/foreign keys to prove the referenced row belongs to the same store.
- Enum-like lifecycle values use reviewed database checks or reference tables. Unknown future values are handled through migrations, not unchecked strings.
- Free-form JSON is restricted to allowlisted event/audit metadata and provider payload fragments. Queryable domain fields remain normalized.
- User-entered text has length limits and normalization rules, but original display casing is preserved where required.

### Identity and access

- `users`: identity-independent profile and lifecycle status.
- `auth_credentials`: password identity, verification state, and password-change metadata; secrets/tokens are hashed.
- `auth_sessions`: hashed opaque session token/family, idle/absolute expiry, rotation lineage, revocation, and last-used metadata.
- `mfa_methods` and single-use `auth_challenges`: administrator MFA and short-lived verification/recovery.
- `stores`: public and operational store data plus lifecycle status.
- `store_memberships`: user-to-store relationship and membership status.
- `store_invitations`: hashed invitation token, target contact, role, expiry, and acceptance state.
- `store_membership_permissions` or constrained roles: delegated access.
- `admin_permissions`: explicit platform administration authorization.

### Catalog and inventory

- `products`: store-owned merchandising record and publication state.
- `product_variants`: specific attribute combination and stable SKU/reference within a store.
- `product_media`: association to verified upload objects.
- `categories`, `attribute_definitions`, and `attribute_values`: controlled taxonomy and valid filter values owned by Products.
- `product_variant_attribute_values`: normalized variant attributes; a uniqueness signature prevents duplicate size/color combinations within a product.
- `inventory_levels`: one authoritative stock row per store/variant for the first single-location release, including `on_hand_quantity`, `reserved_quantity`, and `version`.
- `inventory_movements`: append-only reasoned quantity changes.
- `inventory_holds`: active/released/consumed hold linked to a reservation.

The initial design should keep a product store-owned unless a separately approved canonical cross-store catalog is required. Search can still group or rank similar products without prematurely creating global catalog-master workflows.

### Reservations

- `reservations`: customer, store, state, reference, created/expiry/terminal timestamps.
- `reservation_lines`: exactly one first-release line containing variant, requested quantity, and the display snapshot needed for historical comprehension. A line table preserves a clean future migration path without enabling multi-line behavior.
- Inventory holds reference reservation lines but remain owned by Inventory.
- State transition metadata records actor, time, and safe reason.

### Operations

- `uploads`: object key, owner scope, verification/status, safe metadata.
- `notifications`: user-facing notification and read state.
- `notification_deliveries`: per-channel attempts and outcome.
- `audit_events`: Audit-owned append-only actor/action/target/outcome/correlation and allowlisted safe metadata.
- `audit_exports`: sealed batch range, digest, immutable object reference, export/verification status.
- `outbox_events`: durable integration event delivery state.
- `processed_events`: consumer/event deduplication with retention longer than the maximum replay window.
- `idempotency_records`: scoped request key, request fingerprint, outcome reference, and expiry.
- `operational_policies`: validated non-secret configuration with audit history.

### Relationship and deletion rules

- A store has many memberships and products; a product and all its variants belong to exactly one store.
- A variant has exactly one first-release inventory level. Multiple store locations require a future explicit `store_locations` and location-scoped stock migration rather than overloading the initial row.
- A reservation belongs to one customer and store and contains exactly one line. The line references a same-store variant and owns exactly one Inventory hold.
- Product media references only verified Uploads-owned objects. Removing an association does not immediately delete an object that another allowed reference uses.
- Restrict deletion when reservations, movements, audit, or holds reference data. Public lifecycle transitions and anonymized display snapshots preserve historical comprehension.
- Cascade deletion is limited to private, unreferenced aggregate internals whose loss is explicitly safe. Business ledgers never cascade from user/store deletion.

### Initial index plan

Every index must be confirmed with representative query plans; the baseline includes:

- unique normalized authentication identity and unique hashed active session token;
- unique active `(store_id, user_id)` membership and invitation lookup by hashed token/expiry;
- product listing on `(store_id, status, updated_at, id)` and category/publication access paths;
- unique store SKU/reference and unique product variant attribute signature;
- unique `(store_id, variant_id)` inventory level plus optimistic `version`;
- active holds by `inventory_level_id` and unique reservation-line ownership;
- reservation customer history `(customer_id, created_at desc, id)`, store work queue `(store_id, status, expires_at, id)`, expiry sweep `(status, expires_at)`, and unique public reference;
- outbox dispatch partial index on undispatched `available_at`, processed-event uniqueness by consumer/event, and idempotency lookup by actor/operation/key;
- notification user/unread and pending-delivery indexes;
- audit event time/actor/target indexes selected for governed queries.

Low-cardinality status indexes stand alone only when a partial or composite query plan proves useful.

### Partition and archive policy

Do not partition the transactional core initially. Review monthly time partitioning for `audit_events`, `inventory_movements`, `outbox_events`, and `notification_deliveries` when any table approaches 50 million rows, routine retention jobs exceed their window, or index/backup growth breaches capacity budgets. Partition keys must preserve required uniqueness and query patterns. Reservation and inventory tables remain unpartitioned until measured evidence justifies the migration.

## Inventory concurrency

Reservation correctness is a PostgreSQL responsibility coordinated by the Inventory module.

For each reservation attempt:

1. Start a transaction.
2. Lock the relevant inventory rows in a deterministic order or use an equivalent atomic conditional update.
3. Recalculate available quantity as `on_hand_quantity - reserved_quantity` from authoritative state.
4. Reject if store/product/variant is ineligible or quantity is insufficient.
5. Create the durable reservation and inventory hold and increase `reserved_quantity` consistently.
6. Record movement/hold audit metadata and outbox events.
7. Commit before returning success.

Constraints MUST enforce `0 <= reserved_quantity <= on_hand_quantity` and prevent duplicate active hold application. Fulfillment atomically decrements both quantities and records a movement; cancellation, decline, and expiry decrement only reserved quantity. Idempotency records prevent network retries from repeating the logical operation. Redis locks MUST NOT be the correctness mechanism.

The first release accepts exactly one reservation line. Partial reservation acceptance and multi-line reservations are not approved.

## Search projection

A Meilisearch document should represent the smallest unit required to filter availability correctly, typically a store product or store product variant. It contains:

- opaque authoritative identifiers;
- searchable name/description/category terms;
- approved variant facets;
- public store name and location facets;
- public availability state and freshness;
- verified media reference;
- publication and eligibility fields;
- projection version and authoritative update timestamp.

Search indexing flow:

1. Product, Store, Inventory, or Upload commits an eligibility-relevant change and writes an outbox event.
2. Search consumer loads the current authoritative aggregate/read model.
3. It upserts or deletes the document idempotently.
4. Metrics record event age and indexing result.

Full rebuild writes to a versioned index, validates counts and sample queries, then atomically switches the active index/alias or equivalent application configuration. Incremental events occurring during rebuild must be replayed or dual-applied before cutover.

## Cache design

Every cache entry has:

- an owner module;
- key namespace and version;
- data classification;
- TTL;
- invalidation strategy;
- behavior on Redis failure;
- metrics for hit/miss and errors.

Cache public, frequently read, low-risk data such as store summaries or selected product details only after measuring need. Do not cache permission decisions longer than safe revocation objectives. Reservation availability is always revalidated transactionally.

## Authorization model

Authorization is a policy check over:

- authenticated actor;
- global user status;
- store membership and membership status;
- required permission;
- target store/resource ownership;
- administrative permission when applicable;
- resource lifecycle state.

Routers establish actor context; application services enforce the action-specific policy. Repositories also require tenant keys for store-owned queries as defense in depth. An administrator does not automatically impersonate a store user; support access is explicit and audited.

## Session architecture

The Phase 2.2 authentication design combines short-lived access JWTs with
authoritative opaque refresh sessions:

- each Next.js application exposes the backend API through its same-origin routing/proxy layer;
- authentication issues a 15-minute Ed25519 access JWT containing identity-only claims;
- the opaque refresh credential has at least 256 bits of entropy and is protected by a host-only, `Secure`, `HttpOnly`, `SameSite` cookie in first-party clients;
- PostgreSQL stores the hashed session token/family, user, issued/idle/absolute expiry, rotation lineage, and revocation state; Redis may cache a bounded lookup but is not authoritative;
- refresh rotates into a child session row; reuse revokes the entire family;
- access validation checks both JWT cryptography and authoritative session state;
- dashboard administrator policy requires MFA;
- public frontend and dashboard sessions are separate host-scoped sessions, so compromise of one host does not automatically expose the other's cookie;
- the same account identity may authenticate independently to both applications.

The same-origin proxy only forwards approved API traffic and
correlation/security headers. It contains no domain decisions. ADR 0009 records
the token and key-management decision.

## API boundary

All client traffic goes through versioned FastAPI endpoints. Public and authenticated representations may differ. Responses use dedicated DTOs and never serialize ORM objects. The reviewed OpenAPI document under `docs/api/` is designed before implementation and is the contract authority. FastAPI emits an implementation view that CI must compare for semantic conformance and unexpected drift. API rules are defined in [API Standards](09-api-standards.md).

The frontend and dashboard use the same authoritative API. If server-side Next.js code proxies requests for session or rendering reasons, it remains a transport adapter and cannot become another business backend.

## Failure behavior

| Dependency failure | Required behavior |
|---|---|
| PostgreSQL unavailable | Fail readiness and reject authoritative operations; never fall back to stale writes. |
| Redis unavailable | Bypass optional cache; rate limiting follows documented fail-safe policy; surface degraded health. |
| RabbitMQ unavailable | Authoritative transactions continue writing outbox records; dispatcher backlog and age alert; workers resume idempotently after recovery. |
| Meilisearch unavailable | Search is unavailable/degraded; product writes continue and outbox backlog accumulates for replay. |
| R2 unavailable | New upload/finalization fails safely; existing catalog data remains authoritative. |
| Notification provider unavailable | Business transaction succeeds; delivery retries and alerts. |
| PostHog unavailable | Core request succeeds; analytics is dropped or retried according to bounded policy. |
| Sentry unavailable | Core request succeeds; local structured logging still records the error safely. |

## Phase 1.5 operational foundation

The API exposes three unversioned platform probes:

- `/health/live` confirms only that the process can serve HTTP;
- `/health/startup` confirms that required startup initialization completed;
- `/health/ready` concurrently checks PostgreSQL, RabbitMQ, Redis, Meilisearch,
  and the configured MinIO/R2 endpoint with bounded timeouts.

Readiness failure removes a replica from traffic but does not make liveness fail,
preventing dependency outages from causing restart storms. Probe responses
contain safe status and timing data, never credentials or provider errors.

Prometheus metrics and OpenTelemetry remain cross-cutting adapters around the
modular monolith. They do not create a feature module, system of record, or new
deployment boundary. Metric labels use route templates and dependency names;
business identifiers are prohibited. OpenTelemetry instruments FastAPI,
SQLAlchemy, outbound HTTP, and the Celery/RabbitMQ foundation when enabled.
Sentry is a disabled-by-default error adapter with PII and request bodies
disabled. See [Observability](observability.md).

## Architecture fitness checks

CI SHOULD enforce:

- prohibited imports from domain to framework/infrastructure;
- no cross-module ORM imports;
- module dependency graph without cycles;
- OpenAPI compatibility checks;
- reviewed-contract versus FastAPI conformance checks;
- migration single-head check;
- repository queries scoped by store where applicable;
- domain state-machine and concurrency tests;
- container and dependency policy.

## Architecture decision records

Accepted foundation ADRs are indexed in [`docs/adr/`](adr/README.md). More detailed product decisions are recorded before the affected module is implemented, including:

- authentication/session strategy;
- database identifiers, optimistic versions, lifecycle/deletion, and partition thresholds;
- reservation locking and idempotency design;
- product/store ownership and variant model;
- transactional outbox publisher design;
- RabbitMQ durability, routing, dead-lettering, and operational topology;
- Meilisearch document granularity and rebuild method;
- media delivery/transformation approach;
- hosting topology and managed service selections;
- OpenTofu state/backend and OpenTelemetry/metrics/log destinations;
- notification channels/provider;
- analytics consent and retention implementation.

An ADR records context, decision, alternatives, consequences, rollout, rollback, owner, and date. It does not silently override business requirements.
