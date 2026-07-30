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

## Phase 1.6 — Architecture freeze

### Outcomes

- Establish a reviewed, measured, and tagged foundation before business implementation begins.

### Work

- Audit dead code, generated artifacts, dependencies, TODO markers, documentation, and diagrams.
- Benchmark development startup, health/API paths, PostgreSQL readiness, and memory.
- Review environment variables, secrets, containers, CI, dependencies, headers, and observability.
- Record accepted foundational decisions in ADRs.
- Publish system, module, sequence, empty ER, and request-flow diagrams.

### Exit gate

- The Phase 1.6 review is committed and all CI-equivalent checks pass.
- The reviewed commit is tagged `foundation-v1`.
- Material foundation changes after the tag require an ADR and technical review.

## Phase 2 — Identity & Access

### Outcomes

- Secure identity, sessions, profiles, and role-based access form the trust boundary for every later module.

### Work

- Implement registration, sign-in, verification, recovery, session lifecycle, and account controls.
- Implement user identity profiles without placing store, catalog, or administrator domain rules in the Users module.
- Establish permission evaluation, administrator MFA requirements, audit events, abuse controls, and enumeration-safe errors.
- Add horizontal and vertical authorization contract tests.

### Exit gate

- Session revocation, credential recovery, and permission tests pass.
- Protected APIs consistently reject missing, invalid, expired, and revoked credentials.
- Sensitive values are absent from logs, telemetry, and error reporting.
- Security review approves the identity and access boundary.

## Phase 3 — Store Module

### Outcomes

- Verified stores can be onboarded and operated by explicitly authorized owners and staff.

### Work

- Implement store lifecycle, public profile, verification, suspension, and moderation hooks.
- Implement store memberships, invitations, revocation, and store-scoped permissions.
- Add dashboard store selection and permission-scoped administration foundations.
- Add complete tenant-isolation and authorization tests.

### Exit gate

- Store A cannot read or modify Store B data.
- A store can be submitted, approved, suspended, and restored according to policy.
- Membership changes and administrative actions are audited.
- Representative store operators can complete onboarding.

## Phase 4 — Product Catalog

### Outcomes

- Approved stores can publish structured and verified product information.

### Work

- Implement approved taxonomy and reference data.
- Implement products, variants, drafts, publication, validation, and moderation hooks.
- Implement R2 upload intent/finalization, media verification, and object lifecycle.
- Emit reliable events for eligible store, product, and media changes.
- Build accessible, mobile-ready catalog management workflows.

### Exit gate

- Publication rejects incomplete or unverified content.
- Store isolation applies to every catalog and upload path.
- Upload security and object-permission reviews pass.
- Catalog changes are transactional, audited, and observable.

## Phase 5 — Inventory

### Outcomes

- Stores can maintain accurate stock while public consumers receive only approved availability information.

### Work

- Implement inventory levels, movement ledger, nonnegative constraints, private exact views, public availability mapping, and freshness rules.
- Enforce `0 <= reserved <= on_hand`, versioned mutation, and reconciliation.
- Emit idempotent inventory projection events.
- Keep bulk import outside MVP unless post-pilot evidence promotes it.

### Exit gate

- Concurrent mutations preserve inventory invariants.
- Exact quantities remain private and public availability follows policy.
- Reconciliation detects and safely reports drift.
- Store operators complete core inventory workflows successfully.

## Phase 6 — Search

### Outcomes

- Customers can reliably discover eligible inventory across participating stores.

### Work

- Define and version Meilisearch documents, facets, ranking, synonyms, and typo tolerance.
- Implement idempotent incremental projection and periodic authoritative reconciliation.
- Implement full rebuild with safe cutover and a tested runbook.
- Build the search API contract without coupling authoritative writes to Meilisearch.
- Instrument governed relevance, success, zero-result, freshness, and latency measures.

### Exit gate

- Eligible sampled records are present and ineligible records are excluded.
- Search freshness and latency targets pass representative tests.
- Rebuild, replay, and reconciliation complete without missing updates.
- Public contracts expose no private inventory or operational fields.

## Phase 7 — Reservations

### Outcomes

- Customers can create safe time-limited holds and stores can process them without overselling.

### Work

- Implement the reservation state machine and human-readable references.
- Implement the Inventory hold acquire, release, and consume contract.
- Use PostgreSQL transactional concurrency controls and persistent idempotency records.
- Implement customer and store reservation workflows, expiry jobs, reconciliation, and transactional notifications.
- Test contention, retries, duplicate delivery, delayed expiry, and provider outages.

### Exit gate

- High-contention tests prove that stock cannot be oversubscribed.
- Every terminal transition changes a hold exactly once.
- API retries and Celery redelivery are logically idempotent.
- Notification failure cannot corrupt reservation state.

## Phase 8 — Customer Website

### Outcomes

- Customers have an accessible, responsive discovery and reservation experience.

### Work

- Build public discovery, product detail, store detail, account, and reservation views.
- Integrate search and reservation contracts through generated clients.
- Add safe public caching and conditional responses where measurements justify them.
- Validate responsive behavior, WCAG 2.2 AA acceptance, privacy controls, and analytics governance.

### Exit gate

- Critical customer journeys pass browser, accessibility, and mobile tests.
- The UI clearly communicates availability, reservation expiry, and the platform's non-commerce boundary.
- Performance budgets pass on representative devices and networks.
- Analytics collection follows approved consent and data-minimization rules.

## Phase 9 — Store Dashboard

### Outcomes

- Store owners and staff can operate their approved store capabilities efficiently and safely.

### Work

- Complete store, membership, catalog, upload, inventory, and reservation workflows.
- Apply role and store scope to navigation, actions, APIs, and generated client usage.
- Add operational feedback, safe retry behavior, accessibility, and mobile usability.
- Add store-scoped analytics only for approved definitions.

### Exit gate

- Role-based end-to-end tests cover owner and staff workflows.
- Cross-store data exposure is absent from UI and API behavior.
- Representative store users complete critical workflows within accepted usability criteria.
- Failures are actionable without exposing internal or sensitive data.

## Phase 10 — Admin Platform

### Outcomes

- Authorized operators can moderate, support, observe, and launch the network safely.

### Work

- Complete verification, suspension, moderation, support, audit-query, and field-masking workflows.
- Complete platform aggregate metrics and approved PostHog dashboards.
- Conduct performance, accessibility, resilience, backup/restore, disaster-recovery, RabbitMQ redelivery, search rebuild, and penetration exercises.
- Tune measured bottlenecks and finalize incident, rollback, queue, recovery, and operator runbooks.
- Run a controlled pilot with explicit go/no-go gates before wider launch.

### Exit gate

- All P0 acceptance evidence is linked and no critical or high launch blocker remains.
- Recovery, rollback/roll-forward, search rebuild, and incident exercises pass.
- On-call ownership, alerts, dashboards, and support escalation are active.
- The controlled pilot has no unresolved isolation or inventory-integrity issue.
- Product, technical, security, and operational owners approve wider release.

## Post-launch improvement

Only prioritize evidence-backed improvements within product scope: search relevance, taxonomy, inventory freshness, store onboarding, performance/cost, accessibility/localization, reporting definitions, dependency upgrades, and bulk import if pilot evidence supports it.

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
