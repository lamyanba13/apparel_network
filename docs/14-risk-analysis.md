# Risk Analysis

## Risk management method

Risks are reviewed at sprint planning, architecture review, release review, and after incidents. Each active risk has an owner, evidence, mitigation tasks, trigger indicators, contingency, review date, and residual rating.

Likelihood and impact use a 1–5 scale:

- Likelihood: 1 rare, 2 unlikely, 3 possible, 4 likely, 5 almost certain.
- Impact: 1 negligible, 2 minor, 3 material, 4 major, 5 critical.
- Score: likelihood × impact.
- Rating: 1–4 low, 5–9 medium, 10–16 high, 17–25 critical.

Scores guide attention but do not override a lower-probability security or safety issue with unacceptable impact.

## Initial risk register

| ID | Risk | L | I | Score | Primary mitigation | Trigger/indicator | Contingency | Owner |
|---|---|---:|---:|---:|---|---|---|---|
| R-01 | Store inventory becomes stale, reducing customer trust. | 4 | 5 | 20 | Show freshness; simple update flows; stale warnings; measure freshness; define store operating policy. | Rising stale-stock age, failed reservations, customer reports. | Reduce/hide stale availability per policy; contact store; temporarily unpublish unreliable records/store. | Product + Store Operations |
| R-02 | Concurrent reservations oversubscribe physical stock. | 3 | 5 | 15 | PostgreSQL locking/atomic updates, constraints, idempotency, deterministic state machine, contention tests. | Negative/invalid reconciliation, high conflict anomaly. | Disable reservations via safe flag while preserving search; reconcile holds; incident review. | Inventory/Reservations Engineering |
| R-03 | Cross-store or cross-customer data leakage. | 3 | 5 | 15 | Deny-by-default policies, tenant-scoped repositories, object/list tests, granular admin permissions, review. | Authorization anomaly or report. | Contain affected routes/accounts, revoke sessions, investigate/notify per incident policy. | Security + Feature Owner |
| R-04 | Search exposes suspended, unpublished, or private data due to projection lag/bug. | 3 | 5 | 15 | Minimal public index schema, eligibility events, reconciliation, detail revalidation, safe rebuild and tests. | Search/database mismatch, forbidden-field scan, suspension lag. | Remove affected index/documents, disable search if necessary, rebuild from PostgreSQL. | Search Engineering |
| R-05 | Store personnel find data entry too difficult and stop updating inventory. | 4 | 4 | 16 | Mobile-first workflows, usability testing, clear validation, onboarding/training; bulk import if validated. | Low active-store/freshness rates, support burden, abandonment. | Simplify required catalog fields/workflows; assisted onboarding within normal controls. | Product + Design |
| R-06 | Product taxonomy and inconsistent store data cause poor relevance. | 4 | 4 | 16 | Controlled categories/attributes, normalization, quality validation, query evaluation set, synonyms. | High zero-result rate, irrelevant results, filter gaps. | Curate taxonomy/synonyms, correct data, adjust ranking with versioned rollback. | Product + Search |
| R-07 | Authentication or recovery compromise leads to account takeover. | 3 | 5 | 15 | Adaptive hashes, secure sessions, rate limits, enumeration resistance, MFA for admins, alerts, threat tests. | Credential-stuffing spike, token reuse, suspicious session behavior. | Force revocation/reset, block sources, rotate keys, incident response. | Security + Auth |
| R-08 | Malicious uploads create active content, malware, cost, or data exposure. | 3 | 5 | 15 | Strict allowlists, validation/re-encoding/scanning, private pending objects, quotas, signed scopes, cleanup. | Validation failures, unexpected content type, storage/egress spike. | Suspend uploads, quarantine/remove objects, rotate storage credentials, inspect access. | Uploads + Security |
| R-09 | Background queue outage delays search, notifications, or expiry. | 3 | 4 | 12 | Durable outbox, idempotent tasks, backlog/age alerts, separated queues, recovery/reconciliation. | Oldest-task/outbox age, expiry delay, delivery failure. | Scale/restart consumers, prioritize critical queues, replay, run reconciliation. | Platform |
| R-10 | Meilisearch failure makes the core discovery experience unavailable. | 3 | 4 | 12 | Health/alerts, persistent service, capacity planning, config backup, full rebuild, optional degraded messaging. | Search error/SLO breach, index corruption, disk saturation. | Fail clearly, restore/rebuild/switch index; continue authoritative store operations. | Platform + Search |
| R-11 | Unsafe database migration causes downtime or data loss. | 2 | 5 | 10 | Expand/migrate/contract, production-like tests, backup/PITR, migration review, bounded backfills. | Long locks, error spike, failed validation. | Stop rollout; rollback app if compatible or roll forward; restore only under disaster procedure. | Backend + Platform |
| R-12 | Third-party provider outage or policy change affects R2, notifications, Sentry, or PostHog. | 3 | 3 | 9 | Adapter ports, timeouts, asynchronous calls, bounded retries, data export/config ownership, vendor review. | Provider health errors, pricing/terms notice. | Degrade noncritical capability; switch adapter/provider through controlled migration if sustained. | Platform + Product |
| R-13 | Costs rise unexpectedly through search, storage, egress, analytics, or abuse. | 3 | 4 | 12 | Budgets/alerts, quotas, rate limits, media sizes/lifecycle, cost-per-unit dashboard, capacity review. | Budget threshold, anomalous egress/events/index growth. | Rate-limit/disable abusive paths; lower retention; optimize; revise service tier. | CTO/Platform |
| R-14 | Insufficient observability prolongs incidents. | 3 | 4 | 12 | Request/event correlation, metrics/logs/Sentry, business integrity monitors, runbooks and drills. | Unexplained support issue, alert without diagnosis, missing traces. | Increase temporary safe diagnostics; incident commander assigns instrumentation remediation. | Platform |
| R-15 | Analytics or logs collect excessive personal/private data. | 3 | 5 | 15 | Tracking plan, classification, allowlisted properties, Sentry/log scrubbing, consent/retention, access review. | Unexpected property/body, privacy request, vendor scan. | Stop collection, delete/export per provider ability and policy, notify/assess incident. | Privacy + Analytics |
| R-16 | Scope expands into e-commerce, delaying core discovery. | 4 | 4 | 16 | Vision decision test, requirement traceability, product change control, explicit out-of-scope list. | Cart/payment/delivery work enters backlog without decision. | Remove from active plan; run separate business discovery and re-baseline only if approved. | Product/CTO |
| R-17 | Modular monolith erodes into tightly coupled feature code. | 3 | 4 | 12 | Module ownership, dependency rules, facades/events, architecture tests, ADR review. | Cross-module ORM imports, circular dependencies, global shared growth. | Stop feature expansion in affected area; refactor boundary with characterization tests. | Lead Architect |
| R-18 | Premature microservice extraction adds operational failure modes. | 2 | 4 | 8 | Modular-monolith mandate, scale measurements, extraction ADR gate. | Service proposal without proven independent scaling/team boundary. | Reject/defer; scale stateless monolith/queues/database/search first. | CTO/Architect |
| R-19 | Backups exist but recovery cannot meet objectives. | 2 | 5 | 10 | Quarterly restore and disaster exercises, app-level validation, owned runbooks. | Restore failure or RTO miss. | Treat as high-priority reliability incident; fix procedure/provider/config; increase redundancy. | Platform |
| R-20 | Low bandwidth/device limitations reduce regional usability. | 4 | 3 | 12 | Mobile performance budgets, optimized media, pagination, resilient errors/retry, real-device testing. | Poor Core Web Vitals, abandonment by network/device segment. | Reduce payload/media, simplify flows, defer nonessential scripts/analytics. | Frontend + Design |
| R-21 | Administrative privilege is abused or compromised. | 2 | 5 | 10 | MFA, granular permissions, no implicit impersonation, sensitive-access audit, least privilege, access reviews. | Unusual bulk/sensitive reads, privilege change, off-hours actions. | Revoke access/sessions, preserve audit evidence, incident response, rotate credentials. | Security + Operations |
| R-22 | One store/product model is chosen incorrectly, causing duplicate catalog work or migration. | 3 | 3 | 9 | Validate workflows; ADR store-owned initial product model; avoid premature global master catalog. | Excessive duplicate correction, inability to represent store-specific items. | Add governed canonical linkage later through expand/migrate design without changing store ownership. | Product + Data Architecture |
| R-23 | Reservation notifications create customer expectation of guaranteed purchase. | 3 | 4 | 12 | Clear copy that it is a time-limited hold fulfilled by store; consistent expiry/status; store training. | Disputes/support reports, low fulfillment despite active status. | Adjust wording/policy, require acknowledgement step only if product approves, suspend store reservations if unreliable. | Product + Legal/Operations |
| R-24 | Store staff share owner credentials instead of using memberships. | 3 | 4 | 12 | Simple invitation flow, individual audit, owner education, session anomaly monitoring. | Concurrent geographies/devices, unverifiable action ownership. | Force credential reset/session revoke; assist staff onboarding; restrict affected account. | Store Operations + Auth |
| R-25 | Meilisearch Community/single-node capacity or availability is exceeded before a scale review. | 3 | 5 | 15 | Track documents/rebuild time/memory/latency; adapter boundary; 10,000-store gate; Enterprise sharding or engine migration ADR. | Rebuild misses window, memory/disk saturation, HA requirement, forecast approaches 10 million documents. | Freeze onboarding/index growth, scale vertically, reduce document shape, or execute approved distributed/migration plan. | Search + CTO |
| R-26 | RabbitMQ adds operational complexity or is misconfigured, causing task loss/backlog. | 2 | 4 | 8 | Managed service, durable queues, confirms, TLS, alerts, runbooks, outbox/reconciliation, local parity. | Publish/ack failures, dead letters, disk alarm, missing consumers. | Stop noncritical producers, recover broker, replay outbox/reconciliation, restore topology from code. | Platform |
| R-27 | OpenAPI contract and FastAPI implementation drift. | 3 | 4 | 12 | Design-first source, generated client, semantic conformance CI, breaking-change review, stable operation IDs. | CI drift, frontend workaround, undocumented response. | Block release, restore contract compatibility, version breaking behavior. | API Owner |
| R-28 | Audit data is altered or lost with the primary database. | 2 | 5 | 10 | Append-only runtime role, sealed digest batches, independent restricted archive, restore verification. | Audit sequence/export gap, permission drift, digest mismatch. | Security incident, preserve provider logs, restore archive, rotate access, rebuild allowed evidence. | Security + Audit |
| R-29 | Infrastructure remains manually configured and environments drift. | 3 | 4 | 12 | OpenTofu, remote state/locking, reviewed saved plans, drift detection, emergency-change reconciliation. | Console-only resource, staging/production difference, unexplained policy change. | Freeze deployments, import/reconcile state, review access and drift. | Platform |
| R-30 | Local substitutes mask R2/email/observability provider incompatibility. | 3 | 3 | 9 | MinIO/Mailpit for speed plus staging contract tests against real providers and environment-specific smoke checks. | Staging-only upload/header/provider failure. | Block promotion, update adapter/contract tests, retain local substitute only for supported common behavior. | Platform + Feature Owner |

## Risk treatment rules

- Critical risks require an active mitigation plan before dependent launch work proceeds.
- High risks require sprint-level tasks, an owner, and review date.
- Medium risks require monitoring and planned mitigation or explicit acceptance.
- Low risks remain recorded if triggers may change.
- Risk acceptance states business reason, duration, compensating control, approver, and expiry.
- A risk is closed only with evidence; it may instead become a monitored operational condition.

## Key risk scenarios

### Inventory says available, store has none

The platform should not hide the nature of the data. Show freshness, allow store correction, measure reservation declines, and apply stale/unreliable publication policy. Do not “solve” this by claiming guaranteed availability.

### Two customers reserve the last item

Only one transaction may acquire the remaining hold. The other receives a stable availability conflict. Search may still momentarily show availability; reservation creation rechecks PostgreSQL.

### Store suspension while reservations are active

New discovery and reservations stop immediately within the projection objective. An idempotent background operation cancels existing active reservations, releases their holds, and notifies both parties. Failures remain visible in an administrative reconciliation queue; records are retained rather than deleted.

### Search index contains a private field

Treat as a security incident. Remove/disable the index, identify access/exposure through logs, rebuild from an allowlisted document schema, notify according to incident policy, and add a forbidden-field contract test.

### Worker outage passes reservation expiry

The authoritative `expires_at` controls validity even before the worker updates state. APIs must treat overdue active reservations consistently according to domain policy, and the recovery worker idempotently expires/releases them. Store UI must not fulfill an effectively expired hold if policy forbids it.

### Growth approaches 10,000 or 100,000 stores

The current architecture remains a modular monolith, but the deployment topology is not blindly extrapolated. Before 10,000 stores, run the documented search HA/capacity, PostgreSQL ledger, queue recovery, and cost review. Before 100,000 stores, approve a distributed Meilisearch Enterprise topology or search-engine migration, data/archive partition strategy, multi-region recovery posture, and team/on-call capacity. Missing the gate is a launch/onboarding risk, not a reason to add microservices in advance.

## Risk review evidence

The risk owner updates:

- current score and rationale;
- mitigation progress;
- metrics or incident evidence;
- newly introduced dependencies;
- residual risk after mitigation;
- contingency readiness/drill result;
- next review date.

Release review includes the top risks, any expired acceptances, and whether scope or real usage changed likelihood/impact.
