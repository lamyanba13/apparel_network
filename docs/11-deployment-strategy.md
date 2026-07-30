# Deployment Strategy

## Objectives

The deployment strategy provides repeatable, auditable releases with minimal downtime, safe schema evolution, fast rollback or roll-forward, and clear environment separation. The hosting provider remains an ADR because business jurisdiction, support, and cost inputs are not specified; OpenTofu is the approved infrastructure-as-code tool and keeps provider selection portable.

## Environment model

| Environment | Purpose | Data policy | Deployment |
|---|---|---|---|
| Local | Individual development and tests. | Synthetic fixtures only. | Developer controlled with containers for dependencies. |
| CI ephemeral | Automated validation and preview tests. | Generated synthetic data; destroyed after run. | Per workflow/PR as needed. |
| Development | Shared integration of the `develop` branch. | Synthetic/non-sensitive. | Automatic after `develop` passes. |
| Staging | Production-like release verification. | Synthetic or irreversibly sanitized; never copied raw production data casually. | Promote an approved release-candidate artifact. |
| Production | Customer and store operation. | Real classified data. | Protected, approval-gated promotion from tagged `main`. |

Each environment has separate databases, Redis, RabbitMQ virtual hosts/credentials, Meilisearch, R2 buckets/prefixes and credentials, Sentry environment, PostHog configuration, domains, encryption keys, and provider permissions. Staging cannot send real customer notifications without an explicit safe allowlist.

## Production topology

The initial topology should use managed stateful services and containerized stateless applications:

- edge/DNS/TLS and optional CDN/WAF;
- public Next.js replicas;
- dashboard Next.js replicas;
- FastAPI replicas behind a health-aware load balancer;
- Celery workers, separated into workload queues when required;
- one safe recurring-task scheduler;
- managed PostgreSQL with automated backups/PITR;
- managed or securely operated Redis;
- managed RabbitMQ or an equivalently supported clustered RabbitMQ deployment;
- Meilisearch with persistent storage, backups/config export, and rebuild capability;
- Cloudflare R2 private buckets;
- centralized logs, metrics/alerts, Sentry, and PostHog;
- an OpenTelemetry Collector exporting to managed Prometheus-compatible metrics, Grafana-compatible dashboards, and selected trace/log destinations.

No module is independently deployed as a microservice. API and worker process counts can scale independently from the same backend release artifact.

The initial runtime is a managed container PaaS or equivalent provider service, not Kubernetes. Kubernetes becomes eligible only when measured scheduling, networking, tenancy, or portability requirements outweigh its on-call and upgrade burden.

## Networking and ingress

- Public DNS exposes only the customer frontend, dashboard, and approved API/edge routes.
- PostgreSQL, Redis, RabbitMQ, Meilisearch, administrative endpoints, metrics, and management UIs remain on private networks or provider-private access paths.
- Environment networks/accounts/projects are isolated; production has no trust path from development.
- Ingress terminates TLS, enforces request/header/body limits, preserves a validated client-IP chain, and applies edge rate/WAF controls where available.
- Egress is deny-by-default where the platform supports practical policies; allow only required R2, email, Sentry, PostHog, and control-plane destinations.
- Security groups/firewalls allow only application-to-required-service flows.

Nginx is not a mandatory application container. A managed load balancer/ingress/CDN should own TLS and routing. Add Nginx only if the chosen hosting platform lacks required buffering, compression, static delivery, or proxy controls; doing so requires health, patching, configuration testing, and one clear ownership boundary. Local development uses direct loopback ports and same-origin Next.js proxy behavior, not a production-like Nginx dependency.

## Infrastructure as code

- OpenTofu manages networks, service instances, identities, buckets, DNS, monitoring integration, and non-secret environment configuration supported by providers.
- State is remote, encrypted, locked, versioned, environment-separated, and readable only by platform roles.
- Pull requests run formatting, validation, policy/security scanning, and a saved plan with sensitive output suppressed.
- Production apply uses the reviewed saved plan through a protected GitHub environment and short-lived OIDC identity.
- Manual console changes are emergency-only, audited, and imported/reconciled into OpenTofu immediately afterward.

## Container standards

- Build immutable production images with multi-stage Dockerfiles.
- Pin runtime base images by approved version/digest.
- Run as a non-root user with a read-only filesystem where compatible.
- Include only runtime dependencies; exclude source-control metadata, tests, local files, and secrets.
- Provide liveness/readiness endpoints without leaking dependency details.
- Handle termination signals and allow in-flight requests/tasks a bounded graceful shutdown.
- Set resource requests/limits in the selected runtime.
- Tag images with commit SHA and release identifier; never deploy mutable `latest`.
- Generate and retain SBOM and vulnerability-scan results.
- Build once, promote the same image digest between environments.

## Configuration and secrets

Application configuration uses validated environment variables or mounted secret references. Startup fails fast when required configuration is absent or invalid. Environment variables are transport, not the secret-management system. Configuration categories:

- safe environment configuration: hosts, feature policy defaults, timeouts, log level;
- secrets: database credentials, signing keys, provider credentials, Sentry DSN if classified, PostHog keys according to client/server visibility;
- release metadata: environment, commit SHA, build timestamp, API compatibility flags.

Secret values are provisioned by the environment's secret manager and never generated inside CI logs. Use GitHub Actions OIDC to obtain short-lived deployment credentials where the provider supports it.

## CI pipeline

Pull-request validation runs only relevant jobs where safe, but the protected merge gate covers:

1. repository formatting and lint;
2. Python and TypeScript type checks;
3. unit tests;
4. PostgreSQL/Redis/RabbitMQ/Meilisearch integration tests;
5. architecture dependency tests;
6. reviewed OpenAPI lint/breaking-change and FastAPI conformance checks;
7. migration single-head and upgrade tests;
8. frontend builds and component/accessibility checks;
9. critical end-to-end tests;
10. secret, dependency, static, container, and OpenTofu scans;
11. production image build;
12. documentation/link validation.

Untrusted pull requests do not receive secrets or production-capable credentials.

## CD pipeline

### Development

After merge to the protected `develop` branch:

1. use the already validated commit to build/sign immutable images if not built in CI;
2. publish images to the registry;
3. apply safe infrastructure/config changes;
4. run database expansion migrations through a dedicated migration identity/job;
5. deploy API and workers;
6. deploy compatible frontends;
7. run smoke checks;
8. report release to Sentry and deployment observability.

### Staging

Promote a specific artifact:

1. verify artifact provenance and scan policy;
2. snapshot/confirm backup posture where applicable;
3. apply migrations;
4. deploy using production-equivalent strategy;
5. execute smoke, end-to-end, migration, tenant-isolation, and search-index checks;
6. verify dashboards/alerts and worker queues;
7. record approval evidence.

### Production

Production requires protected-environment approval:

1. confirm change record, owner, rollback/roll-forward, migration plan, and incident contact;
2. verify current database backup/PITR and service health;
3. apply backward-compatible expansion migrations;
4. deploy backend canary or rolling replicas;
5. check errors, latency, saturation, database connections, queue depth, and business smoke tests;
6. deploy frontends compatible with both old and new API during rollout;
7. scale rollout to all replicas;
8. complete post-deploy validation;
9. run backfills asynchronously if applicable;
10. schedule contract/column cleanup only after old code is absent and verification is complete.

## Release strategy

Use rolling deployments initially. Canary release is recommended for backend or frontend changes with high blast radius if the hosting platform supports controlled traffic. Blue/green MAY be used where its operational cost is justified.

Readiness removes new replicas from traffic until configuration and required dependencies are reachable. Liveness only detects a stuck process and must not cause restart storms during a shared dependency outage.

Feature flags MAY separate code deployment from user exposure for risky or gradual changes. Flags:

- have an owner, purpose, environments, and expiry/removal date;
- do not weaken authorization or database invariants;
- default safely if the flag provider/config is unavailable;
- are not long-term forks of business logic.

## Database migration strategy

Database changes use expand/migrate/contract:

### Expand

- add nullable/new structures and indexes using low-lock methods;
- deploy code that can read old and new shapes;
- avoid renames/removals in the same release.

### Migrate

- backfill in bounded, resumable batches;
- track progress and failures;
- validate counts, constraints, and application behavior;
- allow both versions to coexist while replicas roll.

### Contract

- switch all reads/writes to the new shape;
- confirm no old release or task uses the old schema;
- enforce final constraints and remove old structures in a later release.

Migration jobs are serialized. Alembic must have one head. A failed destructive migration is generally rolled forward with a corrective migration; downgrade is used only when proven safe.

## Search deployment and rebuild

Search settings and schema are treated as versioned release artifacts.

For breaking index changes:

1. create a versioned index;
2. record the outbox/event boundary;
3. bulk project authoritative records;
4. replay changes since the boundary;
5. validate document counts, forbidden fields, sample queries, filters, ranking, and freshness;
6. switch the active index atomically through alias/config;
7. monitor errors and relevance metrics;
8. retain the old index briefly for rollback, then remove it through an approved cleanup.

Application releases must remain compatible with the active and candidate index shapes during the switch.

## Background worker deployment

- Tasks use stable names and versioned payloads.
- New workers capable of consuming existing tasks deploy before producers emit a new task/event version.
- Old workers drain before removal.
- Long-running tasks checkpoint or are safe to restart.
- Queue depth and oldest-message age are rollout signals.
- Scheduler changes prevent duplicate schedules or make duplicates harmless.
- Terminal failures move to an inspectable failure state/dead-letter process with replay tooling and authorization.

## Rollback and roll-forward

A release is rolled back when the previous artifact remains schema-compatible and rollback is safer than a corrective release. Roll forward when a migration or emitted event makes application rollback unsafe.

Every production change states:

- last known-good artifact;
- database compatibility window;
- whether new events/tasks are backward compatible;
- flag kill switch if applicable;
- data reconciliation required after rollback;
- owner authorized to decide.

Rollback validation covers authentication, public search, store-scoped inventory read/write, a controlled reservation scenario, worker health, and error rate.

## Health checks and release verification

### Liveness

Confirms that the process event loop/server is responsive. It does not require every external dependency.

### Readiness

Confirms the process can serve its role. API readiness at minimum checks safe database reachability and critical initialization. Worker readiness verifies broker configuration/consumer health through platform-appropriate means.

### Smoke tests

Production-safe smoke checks:

- public home/search route returns expected contract;
- known synthetic/operational public store and product detail read succeeds if maintained;
- authenticated checks use a dedicated restricted synthetic account;
- tenant boundary negative check;
- controlled non-customer-impacting worker task;
- search projection freshness indicator;
- no secrets/private exact inventory appear in public responses.

## Monitoring and alerts

Deployments annotate dashboards and Sentry releases. Monitor:

- HTTP request rate, p50/p95/p99 latency, error ratios by route class;
- frontend availability and Core Web Vitals;
- database CPU, storage, connections, slow queries, replication/backup;
- Redis memory, errors, latency, evictions;
- Meilisearch latency, errors, storage, task backlog;
- Celery queue depth, oldest task, retries, terminal failures, runtime;
- RabbitMQ queue depth, unacknowledged messages, consumer count, publish/ack failures, dead letters, and disk/memory alarms;
- outbox unpublished event age;
- search projection lag;
- reservation expiry delay and conflict rates;
- R2/provider errors;
- Sentry new/regressed issues.

OpenTelemetry resource attributes include environment, service/process, and release. High-cardinality user, store, product, reservation, query text, and object identifiers are excluded from metric labels; safe IDs may appear in sampled traces/logs under data-handling rules.

Alert thresholds tie to SLOs or imminent saturation, not arbitrary noise. Each alert links to a runbook.

## Backup and disaster recovery

- PostgreSQL: automated encrypted backups and PITR meeting RPO; quarterly restore tests.
- R2: lifecycle/versioning policy based on media recovery and deletion requirements.
- Meilisearch: configuration/ranking settings backed up or version-controlled; index data rebuildable from PostgreSQL.
- Redis: persistence is not relied on for authoritative state.
- RabbitMQ: durable topology/configuration is reproducible; outbox and PostgreSQL reconciliation recover business effects rather than treating broker queues as the only record.
- GitHub/container registry/infrastructure definitions: protected and recoverable with access ownership.

Disaster exercises validate the stated RTO, not merely the ability to start a database.

## Production access

- Human production access is least privilege, MFA-protected, time-bound where supported, and audited.
- Normal support uses application admin workflows.
- Direct database writes are prohibited as an operational shortcut.
- Break-glass access has dual authorization where practical, expires, and triggers review.
- Deployments originate from protected CI/CD, not developer machines.

## Release checklist

The executable Phase 1.5 gate is maintained in
[Production Deployment Checklist](production-deployment-checklist.md). Backup,
resource, observability, and disaster evidence are defined in
[Backups](backups.md), [Resource Limits](resource-limits.md),
[Observability](observability.md), and
[Disaster Recovery](disaster-recovery.md).

Before approval:

- acceptance tests and security scans pass;
- migration and index compatibility are reviewed;
- observability and runbooks are updated;
- privacy/analytics changes are approved;
- no unowned feature flag or secret is introduced;
- artifact digest and change list are recorded;
- backup and rollback/roll-forward readiness are confirmed.

After deployment:

- smoke checks pass;
- no SLO/error regression is observed through the defined watch window;
- queue/outbox/search lag is healthy;
- Sentry release mapping and source maps work;
- product owner validates material user-visible behavior;
- release notes and any known limitations are recorded.
