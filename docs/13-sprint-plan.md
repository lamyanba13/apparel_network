# Sprint Plan

## Planning assumptions

- Two-week sprints.
- A cross-functional team capable of frontend, backend, platform, design/product, and quality/security work.
- Exact staffing is not assumed; the team adjusts parallel work to capacity.
- The plan covers an initial production-ready pilot, not guaranteed calendar dates.
- Security, accessibility, tests, operations, and documentation are part of every story.
- P1 bulk inventory import begins only after the controlled pilot; manual dashboard maintenance is the MVP workflow.

## Definition of ready

A story enters a sprint only when:

- it cites business/functional requirement IDs;
- user outcome and acceptance criteria are testable;
- designs and copy exist for user-facing behavior;
- authorization actors, store scope, and data classification are specified;
- API/event/data changes are described;
- dependencies and open product decisions are resolved;
- failure, concurrency, retry, accessibility, analytics, and observability needs are identified;
- rollout and migration impact are understood.

Spikes may be ready with a question, timebox, owner, and expected decision artifact.

## Definition of done

A story is done when:

- acceptance criteria pass in the integrated environment;
- code is reviewed and follows module boundaries;
- unit/integration/contract/end-to-end tests appropriate to risk pass;
- authorization and tenant-isolation cases are covered;
- API/OpenAPI and generated client artifacts are current;
- migrations are safe and tested;
- structured logs, metrics, Sentry, and analytics follow standards;
- accessibility checks pass for changed UI;
- security scans pass and threats are updated where needed;
- documentation/runbooks are updated;
- the feature is deployable, observable, and reversible/controllable;
- no known critical correctness/security defect remains.

## Sprint 0 — Decisions and delivery foundation

### Goal

Make implementation safe to start and prove the release path.

### Scope

- Turn the documented baseline taxonomy, reservation, verification, English-language, in-app/email notification, and availability/freshness policies into accepted criteria and configuration.
- Record authentication, reservation locking, outbox, search document, uploads, hosting, and analytics ADRs.
- Initialize the mandated monorepo and ownership.
- Configure strict formatting, lint, type checks, tests, secret/dependency scanning.
- Pin Ruff, Pyright, pytest, ESLint, Prettier, Vitest, Playwright, axe, pre-commit, commitlint, and pnpm workspace conventions.
- Establish local dependencies and environment-variable contract.
- Add PostgreSQL, Redis, RabbitMQ, Meilisearch, MinIO, and Mailpit core Compose services plus opt-in observability/resilience profiles.
- Provision development/staging skeleton.
- Build immutable no-op application images and deploy through CI/CD.
- Establish request IDs, structured logging, Sentry release mapping, health checks, and baseline metrics.
- Establish OpenTofu remote-state/plan workflow and OpenTelemetry Collector export to the selected managed metrics/log destinations.
- Create the reviewed OpenAPI skeleton, conformance gate, event catalog, data dictionary/index plan, and Audit module boundary.

### Acceptance

- One reviewed change reaches staging through protected automation.
- A baseline Alembic migration upgrades a clean database.
- All required architecture/security decisions have an owner and accepted record.
- CI can block a known test, dependency-rule, secret, or migration failure.
- CI can block OpenAPI drift, forbidden audit mutation, unsafe OpenTofu, and RabbitMQ/outbox contract failures.

## Sprint 1 — Authentication and user lifecycle

### Goal

Provide secure account access and recoverable sessions.

### Scope

- Backend Auth and Users module foundations.
- Registration, contact verification, sign-in, refresh/session, sign-out, all-session revocation, and password recovery.
- Public frontend authentication/account shell.
- Dashboard authentication shell.
- Rate limits, enumeration-safe errors, audit events, security headers, CSRF/CORS/cookie controls per ADR.
- Session management and profile endpoints.
- Authentication threat-model tests and Sentry scrubbing verification.

### Acceptance

- FR-AUTH-001 through FR-AUTH-005 and relevant user requirements pass.
- Recovery tokens are expiring/single-use; session revocation is proven.
- Protected APIs reject missing, invalid, expired, and revoked credentials consistently.
- No credentials or personal payloads appear in logs/Sentry.

## Sprint 2 — Stores, memberships, and admin foundation

### Goal

Establish tenant isolation and store onboarding.

### Scope

- Store lifecycle and profile model.
- Memberships, owner/staff permissions, invitations, revocation.
- Store submission and admin approve/reject/suspend/reactivate.
- Public store detail contract.
- Dashboard store context and membership management.
- Explicit admin permissions, MFA enforcement, audit query base.
- Explicit admin permissions, MFA enforcement, Audit module writes, append-only database roles, and permission-scoped audit query base.
- Cross-store and privilege-escalation integration tests.

### Acceptance

- FR-STR-001 through FR-STR-005 pass.
- Store A cannot read/write Store B private resources through object or collection endpoints.
- Revoked membership stops access within the target.
- Suspending a store changes public eligibility and is auditable.

## Sprint 3 — Products, variants, and uploads

### Goal

Let an approved store build a valid publishable catalog.

### Scope

- Taxonomy/reference data.
- Product and variant create/edit/draft/publication validation.
- Upload intent, signed R2 upload, verification/finalization, association, and removal.
- Dashboard catalog and mobile-friendly media workflow.
- Product moderation hook and audit.
- Upload abuse, file validation, tenant, and orphan-safety tests.

### Acceptance

- FR-PRD-001, FR-PRD-002, FR-PRD-004 and P0 upload requirements pass.
- Unverified media and incomplete products cannot publish.
- Signed upload authorization cannot write outside its object/purpose.
- Product/variant uniqueness and lifecycle constraints hold under concurrent requests.

## Sprint 4 — Inventory and store operations

### Goal

Make exact store stock authoritative, auditable, and ready for discovery.

### Scope

- Inventory level, movement ledger, quantity adjustment, and freshness.
- Database constraints and transaction behavior.
- Database constraints for `0 <= reserved <= on_hand`, aggregate versions, and fulfillment/release semantics.
- Exact store inventory list/detail and public availability mapping.
- Dashboard stock editing and movement history.
- Outbox records for store/product/inventory/media changes.
- Document post-pilot bulk-import contracts and keep implementation outside the MVP.
- Inventory performance and tenant tests.
- Inventory/hold/reservation dry-run reconciliation and repair tests.

### Acceptance

- FR-INV-001 through FR-INV-004 and FR-INV-006 pass.
- Negative quantity is impossible through API, concurrency, or direct constrained persistence.
- Every adjustment is attributable and search event is durably recorded after commit.
- Representative store personnel complete mobile stock update successfully.

## Sprint 5 — Search projection and rebuild

### Goal

Create a correct, rebuildable search index.

### Scope

- Versioned Meilisearch schema, searchable/filterable/sortable attributes, ranking, and settings.
- Outbox publisher and idempotent Search consumers.
- Store/product/variant/inventory/media projection.
- Delete/unpublish/suspend behavior.
- Full versioned rebuild, replay, validation, and cutover runbook.
- Search lag, outbox, consumer, and index-health metrics/alerts.
- Periodic search reconciliation for missing, extra, stale, and forbidden-field documents.

### Acceptance

- FR-SRC-005 and FR-SRC-006 pass.
- Sampled and automated reconciliation proves only eligible records exist.
- Duplicate/out-of-order supported events do not regress a newer projection.
- Rebuild during concurrent writes cuts over without missing committed changes.

## Sprint 6 — Customer discovery

### Goal

Deliver fast, accessible cross-store product discovery.

### Scope

- Search API with text, approved facets, sorts, cursor/provider-safe pagination, and standard errors.
- Public search/results, filters, product detail, and store detail.
- Inventory freshness and platform/store ownership wording.
- Search query normalization, synonyms, local vocabulary evaluation.
- Search analytics tracking plan implementation and zero-result measurement.
- Mobile performance, Core Web Vitals, accessibility, and public data review.

### Acceptance

- FR-SRC-001 through FR-SRC-004 and FR-PRD-003 pass.
- Public responses contain no exact/private stock or private store data.
- Search performance/freshness NFRs pass representative tests.
- Keyboard, screen-reader, responsive, and degraded-network acceptance passes.

## Sprint 7 — Reservation correctness

### Goal

Provide atomic, idempotent customer holds without oversubscribing stock.

### Scope

- Reservation aggregate/state machine and display references.
- Inventory acquire/release/consume hold facade.
- Transactional row locking/conditional update and deterministic lock order.
- Idempotency records and request fingerprinting.
- Customer create/list/detail/cancel.
- Store list/detail baseline.
- Outbox events and audit for reservation changes.
- High-contention, duplicate-request, terminal-race, and rollback tests.
- RabbitMQ redelivery/outage and outbox recovery tests.

### Acceptance

- FR-RES-001 through FR-RES-004 and FR-RES-007 pass.
- Competing requests cannot reserve beyond availability.
- Same idempotency key/payload has one logical outcome; changed payload conflicts.
- Cancellation versus store terminal action takes one valid terminal path and changes holds once.

## Sprint 8 — Reservation operations and notifications

### Goal

Complete store fulfillment, expiry, and reliable communication.

### Scope

- Store fulfill/decline workflow and permission checks.
- Expiry scheduler/worker, reconciliation, and expiry-delay metrics.
- In-app notifications and approved external provider adapter.
- Delivery attempts, retry/backoff, preference rules, and failure operations.
- Customer and store reservation experience, status/expiry copy.
- Provider outage, duplicate event/task, delayed worker, and recovery tests.

### Acceptance

- Remaining P0 reservation and notification requirements pass.
- Each reservation terminal path consumes/releases exactly once.
- Expiry backlog can recover safely after workers are unavailable.
- Provider failure does not roll back a reservation and is operationally visible.

## Sprint 9 — Admin, analytics, and operational completion

### Goal

Give authorized operators the tools and measurements required for a pilot.

### Scope

- Store review and moderation queues completion.
- Permission-scoped support reads with field masking and sensitive-access audit.
- Operational policy editing for reservation limits/duration.
- Store-level and platform-level aggregate definitions/views.
- PostHog consent/retention and approved event validation.
- Audit filters/export policy as approved.
- Operations dashboards and runbook completion.

### Acceptance

- P0 Admin and Analytics requirements pass.
- Store owners never receive another store's private aggregates.
- Policy changes validate, audit, and affect new behavior.
- Admin read/write permissions and sensitive-field masking pass security review.

## Sprint 10 — Hardening and pilot readiness

### Goal

Prove production qualities and close launch blockers.

### Scope

- Full load and contention testing against capacity profile.
- Validate the 1,000-store target and model 10,000/100,000-store scale-gate evidence without claiming the initial search topology supports 100 million documents.
- Query/index/cache/worker tuning based on evidence.
- Dependency-loss and queue-backlog resilience exercises.
- PostgreSQL restore/PITR exercise; search rebuild; rollback/roll-forward drill.
- Accessibility audit and remediation.
- Penetration test and remediation.
- Data retention/privacy workflow validation.
- On-call, incident response, store support, and pilot onboarding rehearsal.

### Acceptance

- P0 NFR objectives and launch quality gates have evidence.
- No unresolved critical/high security or correctness issue.
- RPO/RTO, search rebuild, and rollback procedures pass exercises.
- Alerts route to an owner and link to validated runbooks.
- Launch review approves controlled pilot.

## Sprint 11 — Controlled pilot

### Goal

Validate real operations with a limited store cohort and controlled customer exposure.

### Scope

- Onboard and verify pilot stores.
- Assist initial catalog/inventory quality checks without bypassing normal workflows.
- Gradually enable discovery and reservations.
- Daily review of SLOs, search success/zero results, inventory freshness, reservation outcomes, support issues, and feedback.
- Fix launch-blocking defects; defer unrelated enhancements.
- Produce pilot assessment and wider-launch recommendation.

### Acceptance

- Agreed pilot reliability, data-quality, store-operability, and support criteria are met.
- No tenant/inventory integrity incident remains unresolved.
- Product, technical, security, and operations owners sign the go/no-go record.

## Sprint review evidence

Each review demonstrates working behavior in the integrated environment and supplies:

- requirement IDs accepted;
- API/event/schema changes;
- security and tenant tests;
- accessibility results;
- Sentry/metrics/analytics evidence;
- migration/release/runbook updates;
- risks and decisions;
- scope moved with reason.

## Backlog ordering

Order work using:

1. security, privacy, and data integrity;
2. blockers for the next vertical capability;
3. P0 customer/store outcome;
4. reliability and operational readiness;
5. evidence-backed performance/usability;
6. P1 improvements;
7. P2 ideas.

Out-of-scope commerce, logistics, social, advertising, recommendation, or native-app work does not enter these sprints without a new approved roadmap.
