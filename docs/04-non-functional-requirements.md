# Non-functional Requirements

## Purpose

These requirements define measurable quality attributes for the initial production system. Values are launch objectives and must be reviewed using real traffic after release. Measurements exclude planned maintenance unless stated otherwise.

## Availability and reliability

| ID | Requirement | Initial objective | Measurement |
|---|---|---|---|
| NFR-REL-001 | Public discovery and authenticated core APIs MUST be operated as production services. | 99.9% monthly availability. | Synthetic checks and server-side successful request ratio. |
| NFR-REL-002 | Store dashboard core inventory workflows MUST remain available. | 99.5% monthly availability. | Successful requests for defined critical dashboard routes. |
| NFR-REL-003 | PostgreSQL MUST have automated backup and point-in-time recovery. | RPO ≤ 15 minutes; RTO ≤ 4 hours for a declared database disaster. | Scheduled restore exercises and provider evidence. |
| NFR-REL-004 | Search loss MUST be recoverable from PostgreSQL. | Full index rebuild without authoritative data loss; operational target ≤ 2 hours at launch data volume. | Quarterly rebuild exercise. |
| NFR-REL-005 | Background tasks MUST be retry-safe. | No logical duplicate business effect under at-least-once delivery. | Idempotency tests and duplicate-delivery drills. |

An availability SLO is not a promise that stale physical-store information is current. Inventory freshness is measured separately.

## Performance

| ID | Requirement | Initial objective |
|---|---|---|
| NFR-PERF-001 | Public API reads excluding search and media | p95 ≤ 400 ms, p99 ≤ 1 s server time under agreed normal load. |
| NFR-PERF-002 | Search API | p95 ≤ 700 ms end-to-end backend time, including Meilisearch, under agreed normal load. |
| NFR-PERF-003 | Authenticated mutations | p95 ≤ 800 ms excluding asynchronous projection/notification completion. |
| NFR-PERF-004 | Public web experience | Core Web Vitals at the 75th percentile should meet current “good” thresholds on representative mobile traffic. |
| NFR-PERF-005 | Search freshness | 99% of successfully committed eligible changes visible in search within 60 seconds during healthy operation. |
| NFR-PERF-006 | Reservation correctness | Stock validation and hold creation are one database transaction; no oversell is permitted regardless of latency target. |

Performance tests must define dataset size, concurrency, cache state, hardware/service tier, and traffic mix. A percentile without these conditions is not accepted evidence.

## Capacity assumptions

The first load-test profile MUST be configurable and should validate at least:

- 1,000,000 published product variants/search documents for the 1,000-store target;
- 1,000 participating stores;
- 300 requests per second short peak across public reads;
- 50 concurrent inventory mutations;
- 25 concurrent reservation attempts against the same constrained inventory row;
- one million search documents if the chosen document granularity creates multiple store/variant records.

These are engineering test points, not business forecasts. They validate headroom and must be revised when forecasts exist.

### Scale-stage planning envelope

| Stage | Planning shape | Required architecture evidence |
|---|---|---|
| 100 stores | Up to 100,000 variants and ordinary single-region traffic. | One managed PostgreSQL primary, one Meilisearch deployment, stateless app replicas, and basic worker queues meet SLOs with at least 2× measured pilot peak headroom. |
| 1,000 stores | Up to 1 million variants/search documents. | Connection budgets, search rebuild time, queue recovery, backup restore, and the initial load-test profile pass. This is the initial architecture target. |
| 10,000 stores | Up to 10 million variants/documents and materially larger ledgers. | Dedicated broker/cache, read-model isolation, partition decision review, Meilisearch capacity/HA test, and cost model are approved before onboarding crosses the threshold. |
| 100,000 stores | Potentially 100 million variants/documents; actual shape must be reforecast. | Search engine/distributed topology decision, regional/data partition strategy, multi-region recovery decision, archive tiers, and organization/on-call capacity are approved through ADRs. The initial single-node search topology is not claimed to support this stage. |

Store count alone is not an autoscaling signal. Document count, request rate, contention, media volume, ledger growth, rebuild time, recovery throughput, and cost determine each gate.

## Security and privacy

| ID | Requirement |
|---|---|
| NFR-SEC-001 | All external traffic MUST use TLS; internal managed-service connections MUST use encryption in transit where supported. |
| NFR-SEC-002 | Authorization MUST be deny-by-default and enforced by the backend at resource and store scope. |
| NFR-SEC-003 | Secrets MUST be stored outside source control and rotated using an owned procedure. |
| NFR-SEC-004 | Passwords MUST use an approved adaptive password hash; credentials and tokens MUST never be logged. |
| NFR-SEC-005 | Dependencies, containers, and source MUST be scanned in CI with severity-based remediation policy. |
| NFR-SEC-006 | Personally identifiable information MUST be minimized, access-controlled, encrypted by managed storage services, and governed by retention rules. |
| NFR-SEC-007 | Administrative and critical business actions MUST be auditable and protected against silent alteration through restricted write access and retention controls. |
| NFR-SEC-008 | Uploads MUST be allowlisted, size-limited, stored under server-generated keys, and verified before publication. |

See [Security Standards](10-security-standards.md) for implementation controls.

## Data integrity

- PostgreSQL is authoritative for users, stores, products, inventory, reservations, permissions, audit metadata, and operational policies.
- Foreign keys, unique constraints, check constraints, and transactions MUST enforce invariants that cannot safely depend on application code alone.
- Monetary fields are not part of platform transaction processing. If price display is approved, values MUST use fixed-precision decimal plus ISO currency, never binary floating point.
- Timestamps MUST be stored in UTC with timezone-aware types and displayed in the user's intended timezone.
- Destructive business deletion SHOULD use explicit lifecycle states where history or references must remain.
- Migrations MUST be reversible where feasible and use expand/migrate/contract for unsafe changes.
- Search and caches MUST be disposable and rebuildable.
- Mutable business aggregates MUST use an explicit monotonic version where lost-update protection is required. Inventory reservation uses pessimistic/atomic database concurrency in addition to its version.

## Scalability

- API and worker processes MUST be stateless apart from external stores.
- Horizontal scaling MUST not break sessions, idempotency, job handling, or reservation correctness.
- All collection endpoints MUST paginate.
- Expensive list filters MUST have an indexed query plan verified against representative data.
- Worker queues MUST be separated by workload class when long tasks can delay reservation or notification work.
- The modular monolith MUST remain the default; scaling a process type or extracting a service requires measured evidence and an ADR.

## Accessibility and usability

- Customer and dashboard interfaces MUST target WCAG 2.2 AA for supported workflows.
- All core actions MUST be keyboard operable.
- Text, focus indicators, controls, validation, and status announcements MUST meet accessibility requirements.
- Product information MUST not rely only on color to communicate availability.
- Responsive layouts MUST support current common mobile and desktop viewport sizes.
- Error messages MUST state what failed, whether the operation was applied, and a safe recovery action.
- Destructive or irreversible UI actions MUST require explicit confirmation appropriate to their risk.

## Compatibility

- Support policy MUST cover the current and previous major versions of Chrome, Edge, Firefox, and Safari, including mobile Safari and Chrome on Android where available.
- The platform MAY degrade noncritical enhancements on older browsers but MUST not silently corrupt data.
- API compatibility follows the versioning and deprecation policy in [API Standards](09-api-standards.md).

## Observability

- Every request MUST have a correlation/request ID propagated to logs, errors, and asynchronous job metadata.
- Structured logs MUST include environment, service/process, severity, event name, and safe identifiers.
- Metrics MUST cover request rate, errors, latency, saturation, database pool, queue depth/age, job outcomes, search indexing lag, cache health, and reservation expiry delay.
- Backend and worker instrumentation MUST use OpenTelemetry-compatible traces/metrics. Production metrics use a Prometheus-compatible managed backend and Grafana-compatible dashboards; structured logs remain independently queryable.
- Sentry MUST capture unhandled application errors with environment and release metadata while filtering sensitive data.
- Alerts MUST be actionable, routed to an owner, linked to a runbook, and tested.
- Health endpoints MUST distinguish process liveness from dependency readiness.

## Maintainability

- Feature modules MUST follow the dependency rules in the architecture document.
- Code coverage is a risk signal, not the objective. New business rules and state transitions require direct tests.
- CI MUST run formatting, linting, type checking, unit tests, integration tests, migration checks, and security scans appropriate to changed components.
- CI MUST validate the implementation-generated OpenAPI view against the reviewed contract and fail on undocumented or incompatible drift.
- Public APIs and architecture decisions MUST be documented in the same change that implements them.
- No production change may require direct manual modification of database records as its normal workflow.

## Localization and regional behavior

- User-facing strings MUST be externalizable even if launch supports only one language.
- Timezone display MUST be explicit; server calculations use UTC.
- Search normalization must be tested with approved local terms, store names, and product vocabulary.
- Addresses and phone/contact formats must support the launch region without assuming unrelated international structures.

## Backup, recovery, and continuity

- PostgreSQL backups MUST be encrypted, access-controlled, monitored, and restored in a non-production exercise at least quarterly.
- R2 lifecycle/versioning policy MUST match media recovery and privacy deletion needs.
- Infrastructure configuration, Meilisearch settings, and operational policy definitions MUST be version-controlled or exportable.
- Recovery runbooks MUST define decision owner, dependencies, communication, validation, and rollback.
- A restore is successful only after application-level checks validate authentication, tenant isolation, catalog reads, inventory, and reservations.

## Quality gates

A release cannot be promoted when:

- a P0 correctness or security test fails;
- a database migration has not been tested against a production-like copy/shape;
- critical or high exploitable vulnerabilities lack an approved exception;
- rollback/roll-forward steps are unknown;
- required dashboards, alerts, or Sentry release mapping are absent;
- the release violates a published error budget without explicit incident-owner approval.
