# Development Roadmap

## Roadmap principles

The roadmap builds the smallest safe vertical foundation first, then adds capabilities in dependency order. It does not promise calendar dates; staffing, vendor decisions, and validated product policy determine dates. The sprint plan provides an initial sequence using two-week sprints.

Each phase has an exit gate. Work does not advance by declaring code complete while security, operations, migrations, or acceptance evidence remain unfinished.

## Phase 0 — Product and architecture readiness

### Outcomes

- Confirm that stakeholders understand the documented product boundary and baseline launch policies.
- Approve architecture, data ownership, security baseline, and deployment topology.
- Make unknown business decisions before they become hidden code assumptions.

### Work

- Validate the controlled product taxonomy values within the documented required-field policy.
- Prepare the English UI string catalog and WCAG 2.2 AA acceptance process.
- Configure the documented two-hour, five-unit, five-active-reservation policies and approved state transitions.
- Operationalize the documented store verification and moderation policy.
- Record the server-managed session design and select an email delivery provider behind the Notifications adapter.
- Choose the hosting provider, managed PostgreSQL/Redis/RabbitMQ/Meilisearch topology, managed log/metric destinations, and R2 delivery configuration.
- Select the hosting provider while applying the reviewed OpenTofu, managed RabbitMQ, OpenTelemetry, Prometheus/Grafana-compatible, private-network, and managed-container-PaaS decisions.
- Complete threat models and initial data-retention schedule.
- Define logical data model and API capability map.
- Publish the data dictionary, relationship/index/lifecycle plan, OpenAPI-first contract skeleton, event catalog, and Audit module boundary.
- Create ADRs listed in System Architecture.
- Establish metric definitions and PostHog tracking plan.

### Exit gate

- P0 business/functional requirements are approved.
- Baseline launch policies are reflected in acceptance tests and operational configuration.
- Initial threat model has no unowned critical risks.
- Hosting cost estimate, recovery design, and environment plan are approved.
- The 100/1,000/10,000/100,000-store capacity gates have named metrics and review ownership.
- First two implementation sprints meet definition of ready.

## Phase 1 — Engineering foundation

### Outcomes

- Reproducible monorepo, local environment, CI, deployment skeleton, observability, and backend/frontend foundations.

### Work

- Initialize mandated repository structure and ownership.
- Configure formatting, linting, strict typing, tests, secret scanning, dependency scanning, and architecture checks.
- Establish Next.js public and dashboard shells plus shared design tokens.
- Establish FastAPI app factory, module composition, configuration validation, structured errors, request IDs, logging, Sentry, health endpoints, SQLAlchemy unit of work, and Alembic.
- Provision isolated development/staging foundations.
- Establish PostgreSQL, Redis, RabbitMQ, Meilisearch, R2, Celery, outbox/reconciliation skeleton, and local containers.
- Establish MinIO and Mailpit substitutes plus optional observability/resilience Compose profiles.
- Author/version the OpenAPI contract before endpoints, generate frontend client types, and enforce FastAPI conformance.
- Establish the Audit module append-only path and immutable-export proof of concept.
- Establish OpenTofu remote state/plan workflow and OpenTelemetry resource/attribute policy.
- Create baseline runbooks and release process.

### Exit gate

- A no-op vertical request deploys through staging using immutable artifacts.
- Database migration upgrade is tested in CI.
- Logs, Sentry, metrics, health, and release annotation are visible.
- Architecture dependency tests prevent forbidden imports.
- Secret and container scans pass policy.
- The documented Ruff/Pyright/pytest, ESLint/Prettier/Vitest/Playwright, pre-commit, commitlint, and pnpm workspace workflow is reproducible on a clean machine.

## Phase 2 — Identity, users, and store tenancy

### Outcomes

- Secure accounts and store-scoped access form the trust boundary for later features.

### Work

- Implement registration/sign-in/verification/recovery/session lifecycle according to ADR.
- Implement profile and account controls.
- Implement stores, memberships, invitation/revocation, and permission policies.
- Implement store onboarding/review and admin permission foundation.
- Add complete tenant-isolation and authorization contract tests.
- Add security audit events through the Audit module and a permission-scoped Admin audit query foundation.
- Add store/public profile experience and dashboard store selection.

### Exit gate

- Horizontal and vertical authorization tests pass.
- Session revocation and credential-recovery security tests pass.
- Administrator MFA and permissions work in staging.
- A store can be submitted, approved, suspended, and safely scoped.
- Security review approves identity and tenancy foundation.

## Phase 3 — Catalog, uploads, and inventory

### Outcomes

- Approved stores can publish structured, verified, accurate inventory.

### Work

- Implement approved taxonomy/reference data.
- Implement products, variants, drafts/publication, validation, and moderation hooks.
- Implement R2 upload-intent/finalization, media verification, and lifecycle.
- Implement inventory levels, movement ledger, nonnegative constraints, exact private views, public availability mapping, and freshness.
- Enforce `0 <= reserved <= on_hand`, aggregate versions, exact fulfillment/release semantics, and dry-run reconciliation.
- Keep bulk import out of MVP and retain it as P1 post-pilot work.
- Emit outbox events for eligible store/product/inventory/media changes.
- Build store dashboard workflows with mobile usability and accessibility testing.

### Exit gate

- Store A cannot access or modify Store B data in any catalog/inventory path.
- Publication rejects incomplete/unverified content.
- Inventory mutations are transactional, audited, and produce correct availability.
- Upload security test suite and object-permission review pass.
- Representative store users complete core workflows successfully.

## Phase 4 — Search and public discovery

### Outcomes

- Customers can reliably discover eligible inventory across stores.

### Work

- Define/version Meilisearch documents, facets, ranking, synonyms, and typo tolerance.
- Implement incremental projection from outbox events.
- Implement periodic authoritative reconciliation in addition to incremental projection.
- Implement full rebuild with safe cutover and operational runbook.
- Build search API, public discovery UI, product detail, and store detail.
- Add public response caching only where measured and safe.
- Instrument governed search success and zero-result events.
- Run relevance evaluation using approved Manipur/store/product vocabulary.

### Exit gate

- Search includes every eligible sampled record and excludes suspended, unpublished, unavailable-policy, and unverified content.
- Freshness SLO is met in load testing.
- Rebuild and incremental replay complete without missing updates.
- Public contracts expose no private inventory or customer/store operational fields.
- Accessibility, mobile performance, and search relevance acceptance pass.

## Phase 5 — Reservations and notifications

### Outcomes

- Customers can create safe time-limited holds and stores can process them.

### Work

- Implement reservation aggregate/state machine and human-readable references.
- Implement Inventory hold acquisition/release/consume facade.
- Implement PostgreSQL locking/conditional update and idempotency records.
- Implement customer create/list/detail/cancel.
- Implement store list/detail/fulfill/decline.
- Implement expiry scheduler/worker and reconciliation.
- Implement in-app and approved external transactional notifications.
- Add concurrency, duplicate delivery, provider outage, and delayed expiry tests.

### Exit gate

- High-contention tests prove no stock oversubscription.
- Every terminal state changes holds exactly once.
- Duplicate API requests and Celery delivery are logically idempotent.
- Notification failure never corrupts reservation state.
- Customer/store usability tests communicate expiry and platform boundary clearly.
- Security review approves reservation and notification behavior.

## Phase 6 — Admin operations, analytics, and hardening

### Outcomes

- Operators can safely launch, observe, support, and improve the platform.

### Work

- Complete moderation and support views with least privilege and field masking.
- Complete operational policies and audit query controls.
- Add store-scoped and platform aggregate metrics.
- Finalize PostHog consent, events, retention, and dashboards.
- Conduct performance/load, accessibility, resilience, backup/restore, and disaster exercises.
- Exercise RabbitMQ interruption/redelivery, audit archive verification, OpenAPI drift, and the 1,000-store capacity profile.
- Tune queries, indexes, caches, workers, and search.
- Complete penetration testing and remediation.
- Finalize legal/privacy text supplied by authorized owners.
- Complete incident, rollback, search rebuild, queue, and recovery runbooks.
- Conduct store-operator training/pilot support readiness.

### Exit gate

- All P0 functional and non-functional acceptance evidence is linked.
- No open critical/high launch blocker.
- No unresolved scale-gate, data-retention, provider-jurisdiction, or audit-integrity blocker for the approved pilot scope.
- Restore, rollback/roll-forward, search rebuild, and incident exercises pass.
- On-call ownership, alert routing, dashboards, and support escalation are active.
- Product owner and technical/security owners approve launch.

## Phase 7 — Controlled pilot and production launch

### Outcomes

- Validate the system with a small participating-store cohort before wider availability.

### Work

- Onboard a controlled set of approved stores.
- Validate catalog quality and freshness operational process.
- Release customer discovery gradually using feature/traffic controls.
- Watch SLOs, zero-result searches, indexing lag, reservation conflicts, expiry, and store response behavior.
- Run daily pilot triage with product, engineering, and store operations.
- Fix correctness and usability issues before increasing scope.

### Exit gate

- Pilot meets the product-set reliability/freshness/operability criteria.
- No unresolved data-isolation or inventory-integrity issue.
- Support load and store workflows are sustainable.
- A go/no-go review approves wider launch.

## Phase 8 — Post-launch improvement

Only prioritize evidence-backed improvements within product scope:

- search relevance and taxonomy improvements;
- inventory freshness workflows;
- bulk import if deferred;
- store onboarding efficiency;
- performance/cost optimization;
- accessibility and localization improvements;
- reporting definition refinement;
- technical debt and dependency upgrades.

POS integration, native apps, payments, delivery, recommendations, or other out-of-scope capabilities require separate product discovery and architecture decisions.

## Cross-phase workstreams

These never become a final-sprint afterthought:

- security threat modeling and authorization testing;
- accessibility and mobile usability;
- observability and runbooks;
- API/event/data-contract governance;
- migrations and data lifecycle;
- product analytics privacy;
- performance budgets and capacity tests;
- documentation and onboarding.

## Milestone reporting

Report each phase using:

- planned versus accepted capabilities;
- requirement IDs completed;
- quality/SLO evidence;
- security and privacy findings;
- migration/operational readiness;
- risks added, reduced, accepted, or escalated;
- unresolved decisions with owner/date;
- scope changes explicitly approved.

Percent-complete estimates without acceptance evidence are not used as release decisions.
