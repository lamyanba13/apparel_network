# Phase 0 Architecture Review

## Review decision

**Phase 0 Approved**

Fashion Network is ready to begin implementation with Sprint 0/Phase 1 engineering-foundation work. This approval is not a production-launch approval. Provider selection, legal retention decisions, threat-model completion, contract/data artifacts, environment provisioning, and pre-launch security/recovery evidence remain gated work explicitly assigned in the roadmap.

No unresolved Critical or High architecture defect remains in the reviewed documentation. The remaining risks are measurable operating or scale risks with owners, triggers, and contingencies.

## Review scope

The CTO review covered every Phase 0 document for:

- business and functional completeness;
- modular-monolith and Clean Architecture boundaries;
- SOLID, repository, service-layer, and dependency-injection practices;
- OpenAPI-first and event-ready contracts;
- relational model, concurrency, indexing, lifecycle, audit, and migration strategy;
- authentication, authorization, tenant isolation, uploads, secrets, and recovery;
- local development, testing, developer workflow, and contribution governance;
- container, network, infrastructure-as-code, CI/CD, observability, and cloud readiness;
- performance at 100, 1,000, 10,000, and 100,000 stores;
- technology fitness and credible replacement/evolution paths;
- naming, folder ownership, and cross-document consistency.

The review did not create application code, API definitions, database models, UI, infrastructure configuration, or deployment resources.

## Scorecard

| Area | Score | Assessment |
|---|---:|---|
| Architecture | 93/100 | Strong module ownership, inward dependencies, transaction boundaries, outbox/reconciliation, and explicit evolution gates. Remaining points depend on ADRs and implemented fitness tests. |
| Security | 92/100 | Opaque sessions, hybrid RBAC/resource policies, tenant defenses, upload controls, restricted audit path, and recovery gates are appropriate. Final retention/jurisdiction and penetration-test evidence remain pre-launch work. |
| Scalability | 87/100 | Clear 1,000-store target and 10,000/100,000-store checkpoints. The initial Meilisearch topology is deliberately not claimed to support 100 million documents. |
| Maintainability | 94/100 | Feature modules, Clean Architecture, contract-first workflow, explicit tooling, lifecycle conventions, and ADR governance are strong. |
| Developer Experience | 92/100 | Deterministic Compose substitutes, pinned quality tools, generated clients, pre-commit, short-lived branches, and staged test gates are implementation-ready. |
| Deployment | 90/100 | OpenTofu, managed container PaaS, private networking, OIDC, immutable artifacts, safe migrations, and portable telemetry are defined. Hosting-provider details remain an owned ADR. |
| Overall Readiness | 91/100 | Ready to implement; not ready to expose production traffic until the roadmap's launch gates pass. |

Scores represent the quality of the reviewed technical foundation, not completed software.

## Findings and resolutions

### AR-01

- **Severity:** High
- **Problem:** The API was described as FastAPI-generated rather than truly OpenAPI-first.
- **Reason:** Framework output as the design authority encourages accidental contracts, weak frontend coordination, and implementation-driven breaking changes.
- **Recommended solution:** Make `docs/api/openapi.yaml` the reviewed source of truth; design operations before code; generate the TypeScript client; compare FastAPI's implementation view semantically in CI.
- **Expected impact:** Earlier contract review, reliable client generation, fewer integration defects, and controlled API evolution.
- **Status:** Remediated in API, architecture, folder, coding, deployment, roadmap, sprint, and contribution documentation.

### AR-02

- **Severity:** High
- **Problem:** Inventory and reservation data did not specify a durable reserved quantity or complete fulfillment/release invariants.
- **Reason:** Deriving active holds without a firm locked-row invariant can create expensive contention queries, ambiguous adjustments, and oversubscription defects.
- **Recommended solution:** Store `on_hand_quantity` and `reserved_quantity` on the inventory level; enforce `0 <= reserved <= on_hand`; update reserved/on-hand atomically; retain a hold ledger and reconciliation workflow.
- **Expected impact:** Constant-time availability checks, explicit correctness under concurrency, and repairable state.
- **Status:** Remediated across business, functional, architecture, roadmap, sprint, and testing standards.

### AR-03

- **Severity:** High
- **Problem:** Audit behavior was present but had no independent module ownership and Admin appeared to own the query surface and records.
- **Reason:** Administrative functionality must not be able to silently alter the evidence used to review it.
- **Recommended solution:** Add an Audit module with append-only insertion, permission-scoped query ports, self-audited privileged reads, sealed digest batches, and an independent restricted archive.
- **Expected impact:** Clear ownership, better least privilege, stronger incident evidence, and retention/recovery testability.
- **Status:** Remediated. Archive-provider immutability capability remains a production selection gate.

### AR-04

- **Severity:** High
- **Problem:** Redis combined cache/rate-limit concerns with Celery transport.
- **Reason:** Cache eviction, memory policy, persistence, and broker durability have different failure and tuning requirements. A shared failure domain increases lost/backlogged task risk.
- **Recommended solution:** Retain Redis for bounded ephemeral state and use managed RabbitMQ for Celery with durable routing, confirms, acknowledgements, dead letters, and monitoring. Keep outbox and reconciliation because no broker provides exactly-once business effects.
- **Expected impact:** Smaller failure domains, predictable queue operation, and improved recovery.
- **Status:** Remediated throughout stack, architecture, deployment, local development, scaling, risk, and test documentation.

### AR-05

- **Severity:** High
- **Problem:** Capacity planning stopped at 1,000 stores while the review required analysis through 100,000.
- **Reason:** A single Meilisearch/data topology cannot be extrapolated safely from one million to potentially 100 million search documents and multi-billion-row ledgers.
- **Recommended solution:** Make 1,000 stores the initial design target; add mandatory 10,000- and 100,000-store gates covering search distribution/migration, ledger partition/archive, multi-region recovery, cost, and operating-team capacity.
- **Expected impact:** Honest scalability claims and planned evolution without premature microservices.
- **Status:** Remediated in NFR, risk, roadmap, sprint, and scaling documents.

### AR-06

- **Severity:** High
- **Problem:** Sentry and provider-selected monitoring were insufficiently concrete for production operations.
- **Reason:** Error capture does not provide complete SLO, saturation, queue, database, or business-integrity monitoring, and provider-specific instrumentation creates lock-in.
- **Recommended solution:** Standardize OpenTelemetry instrumentation/collector, managed Prometheus-compatible metrics, Grafana-compatible dashboards, structured centralized logs, cardinality policy, and owned alert/runbook links.
- **Expected impact:** Portable diagnostics, actionable alerts, measurable SLOs, and faster incident response.
- **Status:** Remediated.

### AR-07

- **Severity:** Medium
- **Problem:** Infrastructure-as-code was deferred without a default tool or state workflow.
- **Reason:** Manual environment construction creates drift, weak review, and irreproducible recovery.
- **Recommended solution:** Adopt OpenTofu with encrypted locked remote state, reviewed saved plans, protected applies, OIDC identity, environment separation, and drift reconciliation.
- **Expected impact:** Reproducible cloud environments, visible change impact, and lower operational risk.
- **Status:** Remediated; hosting provider remains an ADR because jurisdiction, support, and cost inputs are business-specific.

### AR-08

- **Severity:** Medium
- **Problem:** Local development named cloud dependencies but did not define practical substitutes.
- **Reason:** Requiring cloud accounts slows onboarding and makes tests nondeterministic; omitting substitutes causes adapter behavior to go untested.
- **Recommended solution:** Use PostgreSQL, Redis, RabbitMQ, Meilisearch, MinIO, and Mailpit in the core Compose profile; provide optional observability and resilience profiles; run R2/provider-specific contracts in staging.
- **Expected impact:** One-command onboarding, offline daily development, faster tests, and honest provider compatibility checks.
- **Status:** Remediated.

### AR-09

- **Severity:** Medium
- **Problem:** The image pipeline and delivery strategy were deferred.
- **Reason:** Serving originals harms constrained-network performance, cost, privacy metadata, and upload safety.
- **Recommended solution:** Keep originals private; validate, strip metadata, re-encode, and generate immutable 320/640/960/1440 WebP and compatibility JPEG derivatives without upscaling; publish only after baseline derivatives exist; serve through a media CDN domain.
- **Expected impact:** Faster mobile pages, bounded storage/egress, safer media, and stable cache behavior.
- **Status:** Remediated.

### AR-10

- **Severity:** Medium
- **Problem:** Cloud networking and Nginx ownership were unclear.
- **Reason:** Adding Nginx by convention can duplicate managed ingress, while omitting network policy can expose stateful services and management endpoints.
- **Recommended solution:** Use managed ingress/load balancing and private stateful networks; define ingress limits, trusted proxy handling, environment isolation, egress policy, and firewall flows. Add Nginx only when the selected platform lacks a measured proxy capability.
- **Expected impact:** Smaller patching surface, clearer trust boundaries, and fewer conflicting proxy layers.
- **Status:** Remediated.

### AR-11

- **Severity:** Medium
- **Problem:** Database conventions were incomplete for UUIDs, timestamps, optimistic locking, soft deletion, relationships, and partition triggers.
- **Reason:** Leaving these decisions per feature produces inconsistent schemas, lost updates, dangerous cascades, and premature or late partitioning.
- **Recommended solution:** Standardize UUIDv7 identifiers, UTC timestamps, monotonic aggregate versions, explicit lifecycle states, selective physical deletion, same-store composite integrity, append-only ledgers, an initial index plan, and evidence-triggered partition review.
- **Expected impact:** Predictable schemas, safer concurrency/deletion, better query performance, and controlled growth.
- **Status:** Remediated in architecture, NFR, business lifecycle, scaling, and contribution rules.

### AR-12

- **Severity:** Medium
- **Problem:** Developer tooling and branch/release conventions were principles rather than executable standards.
- **Reason:** Teams otherwise choose conflicting formatters, test runners, package managers, and branching practices.
- **Recommended solution:** Pin Ruff, Pyright, pytest, ESLint, Prettier, Vitest, React Testing Library, Playwright, axe, pre-commit, commitlint, and pnpm workspaces; use short-lived trunk-based branches, squash Conventional Commit titles, and Semantic Versioning for external contracts.
- **Expected impact:** Faster onboarding, lower review noise, deterministic CI, and traceable releases.
- **Status:** Remediated.

### AR-13

- **Severity:** Medium
- **Problem:** Incremental outbox processing lacked periodic authoritative reconciliation.
- **Reason:** Publisher confirmation and consumer deduplication cannot eliminate every loss, bug, or manual/provider inconsistency over a ten-year system life.
- **Recommended solution:** Add inventory/hold/reservation and search eligibility reconciliation with dry-run reporting, idempotent repair, audit, metrics, and operational queues.
- **Expected impact:** Detectable drift, bounded inconsistency duration, and safe repair without direct SQL edits.
- **Status:** Remediated with BR-016, functional requirements, architecture, roadmap, sprint, and risk controls.

### AR-14

- **Severity:** Medium
- **Problem:** Shared frontend assets and generated API client ownership were conditional and could become duplicated across two Next.js applications.
- **Reason:** Duplicate generated clients, design tokens, and lint/type configuration inevitably drift.
- **Recommended solution:** Add narrow pnpm workspace packages for generated API client, accessible UI/tokens, ESLint config, and TypeScript config. Do not put feature business logic in shared packages or add a task orchestrator without evidence.
- **Expected impact:** Consistent contracts and UI foundation without creating a generic shared-code dumping ground.
- **Status:** Remediated.

### AR-15

- **Severity:** Medium
- **Problem:** API pagination, repeated filters, sort syntax, unknown fields, patch semantics, and body/search limits were not concrete enough.
- **Reason:** Client teams would otherwise make incompatible assumptions and expose abusive unbounded behavior.
- **Recommended solution:** Standardize cursor pages (25 default/100 max), repeated filter keys, `sort=field`/`sort=-field`, JSON Merge Patch, rejected unknown mutation fields, 1 MiB JSON default, 200-code-point search text, RFC 9457-style errors, and idempotency rules.
- **Expected impact:** Predictable clients, bounded query cost, clearer validation, and safer retries.
- **Status:** Remediated.

### AR-16

- **Severity:** Medium
- **Problem:** Security review explicitly required a JWT/refresh-token decision, but the consequence needed to be unmistakable across security and API guidance.
- **Reason:** Teams often add long-lived browser JWTs by convention, weakening immediate revocation and complicating XSS/session handling.
- **Recommended solution:** Keep rotating server-managed opaque host-only cookie sessions for first-party web applications; store only hashes; require CSRF and origin validation; reserve JWT for a separately approved machine-integration boundary.
- **Expected impact:** Simpler revocation, smaller token exposure, and clearer future identity-provider seam.
- **Status:** Remediated.

### AR-17

- **Severity:** Medium
- **Problem:** S3 compatibility and Meilisearch scalability could be interpreted as feature-equivalence/unbounded capacity.
- **Reason:** R2 intentionally implements a subset/different semantics of S3, and distributed Meilisearch sharding/replication is edition/version dependent.
- **Recommended solution:** Code only to a contract-tested R2 S3 subset, test staging against R2, keep MinIO local, and make Meilisearch Enterprise/migration an explicit scale gate behind a Search port.
- **Expected impact:** Lower provider-surprise risk and a credible search evolution path.
- **Status:** Remediated.

### AR-18

- **Severity:** Low
- **Problem:** Product success measures had names but no process for numerical pilot thresholds.
- **Reason:** Architecture SLOs cannot substitute for product outcome thresholds, while invented pre-pilot numbers would be false precision.
- **Recommended solution:** Require product owners to publish pilot thresholds after baseline measurement and before wider launch.
- **Expected impact:** Evidence-based launch decisions without misleading goals.
- **Status:** Remediated.

### AR-19

- **Severity:** Low
- **Problem:** README wording implied bulk upload could be part of the initial release while later documents placed it after pilot.
- **Reason:** Scope ambiguity creates planning and acceptance conflicts.
- **Recommended solution:** Make manual dashboard maintenance the MVP and bulk import P1 after the controlled pilot everywhere.
- **Expected impact:** Consistent scope and a smaller, safer pilot.
- **Status:** Remediated.

## Technology review summary

The complete per-technology decision is in [Technology Stack](05-technology-stack.md). The CTO conclusion is:

- Keep Next.js, React, TypeScript, TailwindCSS, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Meilisearch, Celery, Cloudflare R2, Docker, GitHub Actions, Sentry, and PostHog.
- Narrow Redis to cache/rate-limit/ephemeral coordination.
- Add RabbitMQ as the Celery broker for failure-domain and durability reasons.
- Add OpenTelemetry plus managed Prometheus/Grafana-compatible operations.
- Add OpenTofu for reproducible cloud infrastructure.
- Use MinIO and Mailpit locally while retaining real R2/email contract tests in staging.
- Keep Meilisearch behind a Search port and require a distributed-topology or migration decision before scale exceeds the validated envelope.
- Do not introduce Kubernetes, microservices, a second primary database, or another backend framework at Phase 1.

The RabbitMQ recommendation is consistent with Celery's current stable documentation, which describes RabbitMQ as a stable broker and distinguishes its behavior from Redis. Cloudflare documents R2 as S3-compatible while publishing an operation-by-operation compatibility matrix, supporting the local-MinIO-plus-real-R2-contract-test approach. Meilisearch documents sharding and replication as Enterprise capabilities, supporting the explicit scale/license gate. OpenTelemetry is the vendor-neutral instrumentation layer, and OpenTofu provides the reviewed plan/apply infrastructure workflow.

Primary references consulted:

- [Celery stable broker overview](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/)
- [Celery broker selection guidance](https://docs.celeryq.dev/en/latest/getting-started/first-steps-with-celery.html)
- [Cloudflare R2 S3 compatibility matrix](https://developers.cloudflare.com/r2/api/s3/api/)
- [Meilisearch replication and sharding](https://www.meilisearch.com/docs/resources/self_hosting/sharding/overview)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
- [OpenTofu team workflow](https://opentofu.org/docs/intro/core-workflow/)
- [MinIO container/S3-compatible development documentation](https://min.io/docs/minio/container/index.html)

## Improvements made

1. Converted API governance from implementation-generated to OpenAPI-first.
2. Added semantic FastAPI contract conformance and generated-client workflow.
3. Added Audit as a dedicated feature module.
4. Added append-only audit permissions, audited privileged reads, digest exports, and independent archive verification.
5. Separated RabbitMQ task transport from Redis cache/rate limiting.
6. Added broker durability, routing, dead-letter, security, capacity, and recovery rules.
7. Added PostgreSQL reconciliation for critical asynchronous outcomes.
8. Defined `on_hand`, `reserved`, and available inventory invariants and terminal reservation effects.
9. Added inventory/hold/reservation and search drift detection/repair requirements.
10. Standardized UUIDv7, UTC timestamps, monotonic versions, lifecycle states, deletion, foreign-key, and JSON rules.
11. Added a logical entity/relationship inventory including challenges, invitations, taxonomy, deduplication, and audit export records.
12. Added baseline PostgreSQL index plans.
13. Added evidence-based ledger partition/archive triggers.
14. Added explicit 100/1,000/10,000/100,000-store architecture stages.
15. Added Meilisearch capacity, HA, Enterprise, cost, and migration gates.
16. Defined the responsive image processing and CDN strategy.
17. Added MinIO, Mailpit, RabbitMQ, and optional observability/resilience local profiles.
18. Added pnpm shared API-client/UI/config packages without shared feature logic.
19. Standardized Python, TypeScript, test, pre-commit, commit, branch, and release tools.
20. Added OpenTofu, remote-state, plan, OIDC, drift, and protected-apply standards.
21. Added managed-container-PaaS-first and no-premature-Kubernetes guidance.
22. Added private networking, ingress, egress, trusted-proxy, firewall, and Nginx decisions.
23. Added OpenTelemetry, Prometheus-compatible metrics, Grafana-compatible dashboards, and cardinality rules.
24. Clarified the no-browser-JWT decision and hybrid role/resource authorization.
25. Made API limits, filter/sort syntax, merge patch, unknown-field, pagination, and contract versioning concrete.
26. Expanded testing for broker redelivery, outbox recovery, optimistic conflicts, audit permissions, OpenAPI drift, provider compatibility, reconciliation, accessibility, performance, and security.
27. Corrected bulk-import scope consistently.
28. Added product pilot-threshold governance.
29. Expanded risk coverage for search ceiling, broker operations, contract drift, audit loss, infrastructure drift, and local/provider mismatch.
30. Updated every Phase 0 document and the documentation map consistently.

## Remaining risks

These are accepted for implementation because they have explicit gates and do not require speculative architecture now:

| Risk | Current treatment | Next mandatory decision/evidence |
|---|---|---|
| Store-reported inventory can become stale. | Freshness display, simple update flow, monitoring, stale/unreliable publication policy. | Pilot freshness and decline thresholds. |
| Search projection is eventually consistent. | Outbox, idempotent consumer, periodic reconciliation, authoritative detail/reservation checks. | Freshness SLO and rebuild/reconciliation test evidence. |
| Meilisearch initial topology is not a 100-million-document guarantee. | Search port, rebuild source, scale gates, capacity/cost monitoring. | Distributed Meilisearch Enterprise or alternative-engine ADR before the relevant gate. |
| Hosting provider and data jurisdiction are not selected. | OpenTofu/provider portability and environment requirements are fixed. | Sprint 0 ADR using legal, support, latency, and cost inputs. |
| Audit immutable archive capability/provider is not selected. | Separate export/digest design and production gate. | Verify R2 feature support or select a compliant archive destination before production. |
| Legal retention and customer policy wording are not engineering decisions. | Configurable lifecycle, anonymization, archive, and deletion workflows. | Authorized legal/privacy approval before production data. |
| Store workflow adoption is unproven. | Mobile-first design, manual MVP, usability testing, controlled pilot. | Pilot evidence before wider launch or P1 bulk import. |
| RabbitMQ adds a stateful dependency. | Managed service, code-defined topology, outbox/reconciliation, monitoring/runbooks. | Staging failure/recovery exercise and cost approval. |
| Third-party email, Sentry, PostHog, R2, and hosting outages remain possible. | Adapter ports, asynchronous degradation, timeouts, privacy controls, runbooks. | Provider selection and staging contract/resilience tests. |
| 100,000-store organizational support is unknown. | Architecture avoids premature distribution and defines team/on-call gate. | Business forecast, staffing, multi-region and operating-model ADR before that stage. |
| Product KPI targets lack real baseline data. | Measures are defined and pilot threshold process is mandatory. | Product owner publishes thresholds during controlled pilot. |
| Physical-store reality can differ from every digital record. | Clear non-guarantee wording, freshness, reservations, reconciliation, and support policy. | Operational policy and pilot incident data. |

## Implementation entry conditions

Phase 1 may begin when the team accepts this review and creates the Sprint 0 work items. Before feature implementation moves beyond the foundation:

- create the ADRs listed in System Architecture;
- create the data dictionary and reviewed OpenAPI/event contract skeletons;
- provision or approve the local Compose dependency set;
- implement architecture fitness, contract drift, tenant, audit-permission, and migration gates;
- select hosting, secret manager, metrics/log destinations, email provider, and audit archive approach;
- complete the named threat models;
- assign service, alert, runbook, and risk owners.

Production launch still requires the separate launch gates in Security, Deployment, Roadmap, and Sprint Plan.

## Approval statement

The reviewed foundation is coherent, secure enough to implement, operationally realistic for a startup, and explicit about where it stops scaling without another decision. It avoids both under-design in inventory/security contracts and over-design through premature microservices or Kubernetes.

**Phase 0 Approved**
