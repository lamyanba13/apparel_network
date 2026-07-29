# Technology Stack

## Selection principles

The approved stack favors a small number of well-supported technologies, clear ownership, strong type and schema tooling, and operational simplicity. Versions MUST be pinned through lock files or image digests and reviewed on a regular upgrade cadence. This document does not freeze exact versions before implementation; the team must select currently supported stable/LTS versions and record them in an ADR and dependency manifests.

## Stack summary

| Layer | Technology | Role | Important constraints |
|---|---|---|---|
| Customer frontend | Next.js, React, TypeScript, TailwindCSS | Public discovery and customer account/reservation experience. | Use server rendering/caching deliberately; no direct access to databases or private service credentials. |
| Operations dashboard | Next.js, React, TypeScript, TailwindCSS | Store owner, staff, and administrator workflows. | Separate deployable app and authorization-aware UI; backend remains authoritative. |
| Backend | FastAPI | HTTP API, dependency wiring, validation boundary, OpenAPI generation. | One modular-monolith application; thin routers. |
| Persistence | SQLAlchemy | ORM and transaction management. | SQLAlchemy 2-style APIs; repositories own persistence queries. |
| Migrations | Alembic | Versioned PostgreSQL schema changes. | One ordered migration history; forward and rollback/roll-forward plan. |
| Database | PostgreSQL | Authoritative transactional data. | Constraints enforce invariants; managed high-availability production service preferred. |
| Cache/coordination | Redis | Cache, rate-limit state, and short-lived coordination. | Never authoritative for business data; define key namespaces and TTLs; do not share an eviction domain with task transport. |
| Search | Meilisearch | Full-text search, filtering, sorting, and typo tolerance. | Rebuildable projection; no authorization decisions. |
| Background jobs | Celery | Asynchronous indexing, notifications, cleanup, and analytics support. | At-least-once delivery; idempotent tasks; separate queues as needed. |
| Message broker | RabbitMQ | Durable Celery task transport and workload routing. | Managed or clustered in production; publisher confirms, durable queues/messages, dead-letter policy, and no business result storage. |
| Object storage | Cloudflare R2 | Product/store media and controlled upload objects. | Private bucket by default; signed access or controlled public delivery. |
| Containers | Docker | Reproducible local, CI, and runtime packaging. | Multi-stage, non-root, minimal production images; immutable tags/digests. |
| CI/CD | GitHub Actions | Validation, build, security checks, and deployment orchestration. | Protected environments and least-privilege OIDC where supported. |
| Error monitoring | Sentry | Error capture, tracing, releases, source maps. | Scrub PII, credentials, headers, and request bodies by default. |
| Product analytics | PostHog | Governed user-flow and search analytics. | Consent/privacy configuration and event schema required. |
| Telemetry | OpenTelemetry | Vendor-neutral traces and metrics from backend, workers, and supporting processes. | Export through a collector; avoid high-cardinality personal or business-sensitive attributes. |
| Metrics/dashboards | Prometheus-compatible backend and Grafana-compatible dashboards | SLO, saturation, queue, database, search, and business-integrity monitoring. | Managed production service preferred; dashboards and alerts version-controlled. |
| Infrastructure as code | OpenTofu | Reproducible networks, managed services, identities, DNS, storage, monitoring, and environment configuration. | Remote encrypted state, locking, reviewed plans, and protected apply workflow. |

## Technology review decisions

| Technology | Decision | CTO review |
|---|---|---|
| Next.js | Keep | Strong fit for public server-rendered discovery and a separately deployed dashboard. Keep business rules in FastAPI and make caching explicit to avoid split-backend behavior. |
| React | Keep | Mature component model and ecosystem. Accessibility and client-JavaScript budgets are required because framework capability alone does not guarantee a usable mobile experience. |
| TypeScript | Keep | Strict typing materially improves contract use across two web applications. Runtime validation remains mandatory at network boundaries. |
| TailwindCSS | Keep with design-system discipline | Productive for a small team; shared tokens and accessible primitives prevent utility duplication. No second styling framework. |
| FastAPI | Keep | Strong Python typing/OpenAPI integration and suitable modular composition. The reviewed OpenAPI file—not framework-generated output—is the design authority; CI checks implementation conformance. |
| SQLAlchemy | Keep | Mature unit-of-work, mapping, and PostgreSQL support. Use explicit repositories and SQLAlchemy 2-style APIs; do not expose ORM entities. |
| Alembic | Keep | Correct migration tool for SQLAlchemy. Require one head, expand/migrate/contract, production-shaped tests, and bounded backfills. |
| PostgreSQL | Keep | Correct authoritative store for tenancy, inventory, reservation transactions, audit, and outbox. There is no reason to add another primary database. |
| Redis | Keep, narrow responsibility | Excellent bounded cache/rate-limit store. Remove Celery transport from the same failure/eviction domain and never use Redis locks for stock correctness. |
| Meilisearch | Keep with a scale exit gate | Excellent startup search UX and operational simplicity. Community/single-node topology is not assumed to support 100 million documents or strict HA; the Search port and rebuild pipeline preserve a migration or Enterprise sharding path. |
| Celery | Keep | Appropriate mature Python worker ecosystem. Durable task transport, idempotency, outbox/reconciliation, bounded retries, and queue ownership are non-negotiable. |
| Cloudflare R2 | Keep | S3-compatible API, suitable economics, and direct signed upload fit. Code to the tested S3-compatible subset; do not assume every Amazon S3 feature exists. |
| Docker | Keep | Provides reproducible local dependencies and immutable runtime artifacts. Production images remain minimal, non-root, and scanned. |
| GitHub Actions | Keep | Natural repository automation with protected environments and OIDC. Untrusted pull requests receive no deployment secrets. |
| Sentry | Keep | Strong error and trace correlation. It supplements rather than replaces logs, metrics, and SLO dashboards. |
| PostHog | Keep | Fits product/search analytics. Govern through a property allowlist, consent, sampling, and retention; it is not audit or operational telemetry. |

No current core technology warrants replacement. RabbitMQ, OpenTelemetry, a Prometheus/Grafana-compatible observability path, and OpenTofu close responsibilities that the original stack left implicit.

## Frontend approach

### Next.js and React

The public frontend and dashboard are independent applications because they have different audiences, caching profiles, security exposure, and release risks. They MAY share versioned workspace packages for design tokens, UI primitives, generated API types, validation helpers, and tooling.

Use:

- server components for non-interactive reads where they reduce client code and preserve safe caching;
- client components only where browser state or interaction requires them;
- route-level error and loading states;
- an explicit backend-for-frontend access pattern only if documented; do not duplicate business logic in Next.js handlers;
- generated or contract-checked API clients;
- accessible components and progressive enhancement for core flows.

Do not store backend secrets in variables exposed to the browser. Public environment variables are considered public data.

### TypeScript

Enable strict mode. Avoid `any`; use `unknown` at untrusted boundaries and narrow explicitly. Domain identifiers should not be interchangeable merely because each is a string. API payload types should originate from the OpenAPI contract or a controlled shared schema process, not hand-maintained duplicates.

### TailwindCSS

Use design tokens and reusable component variants rather than copying long, inconsistent utility combinations. Accessibility states, responsive behavior, and theming values belong in the shared design system. Business state must remain in features, not styling primitives.

## Backend approach

### FastAPI

FastAPI owns transport concerns:

- routing and API version prefix;
- authentication dependency entry points;
- request parsing and response serialization;
- OpenAPI generation;
- error translation;
- correlation IDs and request middleware.

Routers MUST call application services/use cases. They MUST NOT contain SQLAlchemy queries, cross-module workflows, or business state transitions.

### SQLAlchemy

Use one unit of work/transaction boundary per application operation unless an explicitly documented workflow requires otherwise. ORM models are persistence details and SHOULD NOT leak into API responses. Repository interfaces are defined at the application/domain boundary; PostgreSQL implementations live in infrastructure.

Avoid generic repositories that reduce all aggregates to CRUD. Repositories should express domain queries and concurrency intent, such as locking an inventory row for reservation.

### Alembic

Migrations are reviewed as production changes. Autogenerated migrations are a starting point, not trusted output. Each migration must consider locks, table size, defaults, backfill, rollback, and mixed-version deployment.

## Data services

### PostgreSQL

PostgreSQL holds all authoritative state. Use:

- UUID-style opaque external identifiers;
- database constraints for uniqueness, referential integrity, nonnegative quantities, and valid invariant subsets;
- row locking or atomic conditional updates for inventory reservation;
- indexes based on measured access paths;
- JSON only for data genuinely variable or event metadata, not as an escape from relational design.

### Redis

Approved uses include:

- safe response/query caches with bounded TTL;
- distributed rate-limit counters;
- Celery broker/result needs as selected;
- short-lived locks only where loss does not violate business correctness;
- ephemeral session metadata if the authentication design requires it.

Redis loss must cause performance degradation or recoverable job interruption, not loss of authoritative product, inventory, or reservation state.

### Meilisearch

Index documents are denormalized for customer discovery. The Search module alone owns index schemas, ranking rules, synonyms, stop words, filtering, and rebuild workflows. Search results contain stable PostgreSQL identifiers, and critical detail/reservation operations revalidate against PostgreSQL.

### Cloudflare R2

Clients upload using short-lived, narrowly scoped signed requests. The backend generates object keys and finalizes metadata only after verification. R2 credentials never reach clients.

The launch image pipeline stores a private original, validates and re-encodes it asynchronously, strips metadata, and produces immutable responsive derivatives at approved width classes (initially 320, 640, 960, and 1440 pixels without upscaling) in WebP plus a compatibility JPEG; AVIF may be added only after browser/cost measurement. Publication requires at least the baseline derivative set. Public delivery uses a CDN/custom media domain, content-hashed keys, long immutable caching, a safe placeholder, and maximum pixel/byte limits. Originals are not publicly served.

The adapter uses only the R2-supported S3-compatible subset covered by contract tests. R2 is not assumed to provide unsupported S3 bucket features. Local MinIO verifies ordinary S3 flows, while CI/staging contract tests against R2 detect compatibility differences.

## Asynchronous processing

Celery workers use RabbitMQ as the production broker and call application services rather than duplicating domain rules. Redis is not the Celery broker or business result backend. User-visible operation state is stored in PostgreSQL.

- search projection and full rebuild;
- reservation expiry;
- transactional notification dispatch;
- upload cleanup and optional media processing;
- bulk import execution;
- analytics aggregation where not supplied directly by PostHog.

Celery Beat MAY schedule recurring work, but production scheduling must have a single active scheduler or an equivalent duplicate-safe design. Tasks include stable names, schema-versioned payloads, idempotency strategy, retry/backoff, timeout, and dead-letter/terminal-failure handling.

RabbitMQ uses TLS, least-privilege virtual hosts/users, publisher confirms, durable quorum queues where the managed topology supports them, explicit acknowledgements, dead-letter routing, message TTL/size limits, and queue-specific prefetch. The transactional outbox and periodic reconciliation remain required because broker durability does not create exactly-once business effects.

## Observability tools

Sentry is for errors and selected performance traces, not a replacement for metrics and structured logs. PostHog is for approved product analytics, not audit logging or operational monitoring. OpenTelemetry provides vendor-neutral backend/worker instrumentation through a collector.

The deployment platform must additionally provide or integrate:

- centralized structured logs;
- time-series metrics and alerting;
- service and database health metrics;
- uptime/synthetic monitoring;
- backup monitoring.

Production uses a managed Prometheus-compatible metrics backend and Grafana-compatible dashboards. Logs use the hosting provider's centralized structured-log service or an approved OpenTelemetry-compatible destination. This avoids operating a full observability database stack during the startup phase while preserving portable instrumentation.

## Local development

Docker Compose provides deterministic dependencies without requiring cloud credentials:

| Production dependency | Local substitute | Default behavior |
|---|---|---|
| Managed PostgreSQL | Official PostgreSQL container | Required; migrations and fixtures run against PostgreSQL, never SQLite. |
| Managed Redis | Redis container | Required for cache/rate-limit adapter tests. |
| Managed RabbitMQ | RabbitMQ container with management UI | Required for Celery routing, acknowledgement, and duplicate-delivery tests. |
| Managed Meilisearch | Pinned Meilisearch container | Required for search adapter and rebuild tests. |
| Cloudflare R2 | MinIO container | Required for normal upload flows; staging runs R2-specific contract tests because S3 compatibility is not identical. |
| Email provider | Mailpit | Captures verification and reservation email locally without external delivery. |
| PostHog | In-memory/no-network analytics adapter | Default; an opt-in profile may run or target a nonproduction PostHog project. |
| Sentry | Disabled transport plus structured local errors | Default; a nonproduction DSN is opt-in for integration checks. |
| Managed metrics/logs | Optional OpenTelemetry Collector plus Prometheus/Grafana profile | Core development works without it; observability changes run the profile in CI or locally. |

Docker Compose profiles are `core`, `workers`, `observability`, and `resilience`. The core profile starts only daily dependencies; the resilience profile may add Toxiproxy for latency/outage tests. Frontend and backend processes may run natively for fast feedback, but CI validates container builds.

Local fixtures:

- contain synthetic data only;
- provide multiple stores and roles to test tenant isolation;
- include constrained stock for concurrency tests;
- are deterministic and safe to reset.

One repository bootstrap command validates tool versions, starts the core profile, applies migrations, loads synthetic fixtures, and reports service health. It must be safe to rerun. No developer needs a Cloudflare, email, Sentry, or PostHog credential for ordinary feature work.

## Dependency governance

- Pin direct dependencies and commit lock files.
- Enable automated update proposals with CI validation.
- Review framework and runtime support status quarterly.
- Produce an SBOM for production images.
- Block known exploitable critical/high vulnerabilities unless a time-bound exception names an owner and mitigation.
- Do not add a library when the platform/runtime already provides a clear, maintained solution.

## Prohibited substitutions without ADR

The initial implementation MUST NOT:

- split modules into separately deployed microservices;
- use Meilisearch or Redis as the system of record;
- place domain rules in Next.js applications;
- introduce a second backend framework or ORM;
- add another job system, search engine, primary database, or object store;
- use Redis as the production Celery broker without an approved ADR reversing the reviewed separation;
- introduce Kubernetes before measured PaaS/container-runtime limitations justify its operational cost;
- bypass Alembic with manual production schema changes;
- implement custom cryptography or a custom identity protocol.

An ADR may approve a change only with evidence, migration and rollback plans, ownership, cost, and impact across this documentation.
