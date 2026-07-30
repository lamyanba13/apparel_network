# Disaster Recovery

## Objectives

The initial PostgreSQL disaster objective is RPO at most 15 minutes and RTO at most 4 hours. Search is rebuildable from PostgreSQL with a launch-volume target of two hours. Media recovery depends on the approved R2 versioning/backup policy. Redis is never restored as authoritative data. RabbitMQ topology is reproducible and future business effects are recovered from PostgreSQL outbox/reconciliation.

These are objectives until a production-like exercise records evidence. Quarterly exercises are mandatory.

## Authority and declaration

Only the incident commander with Platform and Data owners may declare disaster recovery. The decision records scope, last known-good time, suspected corruption boundary, selected recovery point, expected data loss, communications owner, and whether the source environment is isolated for evidence.

## Restore order

1. Establish clean identity, network, DNS, secrets, encryption, and observability control planes.
2. Restore PostgreSQL to the approved recovery point in an isolated environment.
3. Validate schema/migration heads, constraints, row counts, timestamps, and integrity checks before application access.
4. Restore object-storage configuration and required media objects/version state.
5. Recreate RabbitMQ virtual host, users, exchanges, queues, bindings, dead-letter policy, and permissions from controlled configuration.
6. Provision empty Redis and allow bounded cache/session/rate-limit recovery according to Phase 2 policy.
7. Provision Meilisearch, apply version-controlled settings, rebuild from PostgreSQL, validate, and cut over.
8. Deploy the exact compatible API and worker image digests with restored secrets/configuration.
9. Reconcile outbox, projections, and pending asynchronous work; scale consumers without overwhelming restored services.
10. Restore frontends/edge traffic gradually after smoke, integrity, and security validation.

## Data-integrity verification

Before traffic:

- PostgreSQL accepts read/write health checks and expected migration heads match;
- constraints and foreign keys validate; database timezone/encoding are correct;
- backup end time and selected recovery point are documented;
- future Phase 2 checks validate tenant isolation, sessions, inventory invariants, holds, reservations, audit sequence/export digests, and outbox continuity;
- media object counts/samples, metadata, private access, and hashes match available inventory;
- Meilisearch document counts and forbidden-field checks match authoritative eligibility;
- RabbitMQ topology matches code and no unknown consumers/producers are connected;
- observability, Sentry release mapping, alerts, and backup monitoring work.

## Cutover and rollback

Reduce DNS TTL before planned exercises where applicable. Keep the failed environment isolated and read-only. Cut over with staged traffic and monitor errors, latency, saturation, queue age, and integrity checks. A rollback to the failed environment is prohibited if corruption or compromise remains possible. If validation fails, stop traffic, preserve the recovered copy, correct the procedure, and repeat from a clean restore.

## Exercise evidence

Record backup identifier, recovery point, start/end times, achieved RPO/RTO, data volume, commands/automation version, validation results, gaps, screenshots/dashboard links, decision owners, and remediation deadlines. A backup is not considered successful until this application-level restore exercise passes.
