# Platform Runbook

## Operating rules

Confirm the environment, incident owner, start time, affected users, and current release before changing state. Prefer reversible actions. Never repair business data with direct SQL. Preserve logs and evidence, record every intervention, and escalate security or integrity symptoms immediately.

Use request/correlation IDs to connect gateway, API, worker, database, and Sentry evidence. Do not paste secrets or customer data into incident channels.

## First response

1. Check external availability, deployment events, liveness, startup, and readiness.
2. Inspect API error ratio/latency, container restarts/resources, database pool, queue age, and dependency dashboards.
3. Identify whether failure began with deployment, configuration, dependency, capacity, or provider change.
4. Stop rollout or reduce exposure when impact is growing.
5. Choose rollback only when schema/event compatibility permits it; otherwise roll forward.
6. Communicate status and next update time.

## High API error rate

- Compare 5xx by route template and release; inspect Sentry regressions and `http.slow_request`.
- Check readiness and dependency metrics. A healthy liveness probe with failed readiness indicates dependency or initialization trouble, not a dead process.
- Check CPU/memory throttling and database pool saturation.
- If release-correlated, stop rollout and follow the documented rollback/roll-forward decision.
- Do not restart all replicas simultaneously; retain evidence and avoid a thundering herd.

## Database unavailable

Symptoms: readiness marks PostgreSQL unhealthy, startup may fail, 5xx rises, pool or provider alarms fire.

1. Verify provider/network/TLS/DNS status and credentials without printing secrets.
2. Check connection limit, pool checked-out count, long transactions, locks, storage, and failover status.
3. Stop noncritical workers/backfills if they consume connections.
4. Do not route authoritative operations to a stale replica.
5. For regional/provider failure, declare disaster recovery and follow `docs/disaster-recovery.md`.
6. After recovery, verify migration heads, connection latency, application reads, and data integrity.

## Database connection pool saturation

- Calculate total possible connections across API replicas, workers, migration jobs, and operational tools.
- Find leaked/long transactions and slow queries before raising pool sizes.
- Apply bounded concurrency/backpressure; raising every replica pool can exhaust PostgreSQL.
- Confirm p95 latency and checked-out connections recover.

## RabbitMQ unavailable

Symptoms: readiness marks RabbitMQ unhealthy, workers disconnect, outbox backlog/age grows, queue alarms appear.

1. Check RabbitMQ node, disk/memory alarms, TLS/certificate, virtual host, credentials, networking, and management status.
2. Pause noncritical producers if backlog growth threatens recovery.
3. Recover the managed cluster/topology; never switch Celery to Redis.
4. Restart or scale consumers gradually, observing downstream PostgreSQL/Meilisearch capacity.
5. Replay from the future transactional outbox and run reconciliation; do not assume broker persistence provides exactly once.
6. Verify consumer count, oldest message age, redeliveries, dead letters, and worker errors.

## Redis unavailable

Symptoms: readiness marks Redis unhealthy, cache/rate-limit/session adapters degrade.

1. Check memory, evictions, max clients, TLS/authentication, networking, and provider status.
2. Preserve the documented fail-open/fail-safe policy by endpoint risk.
3. Do not restore business truth from Redis; PostgreSQL is authoritative.
4. Recover Redis, warm caches gradually, and watch stampede/load effects.
5. Verify no Celery configuration points to Redis.

## Meilisearch unavailable

1. Check process/task queue, CPU/memory/disk, keys, networking, and index health.
2. Keep authoritative product/inventory writes available; search may fail clearly.
3. Recover the service or rebuild a versioned index from PostgreSQL when corruption is suspected.
4. Validate count, forbidden fields, sample queries, settings, and projection freshness before cutover.
5. Treat exposure of private data as a security incident.

## MinIO or R2 unavailable

1. Check provider health, DNS/TLS, credentials, bucket policy, quota, and endpoint reachability.
2. Fail new upload/finalization safely; do not publish unverified objects.
3. Existing authoritative catalog records remain available; use a safe media placeholder if approved.
4. Recover access, verify object integrity and private policy, then reconcile pending uploads.

## Docker or container failures

- Run `docker compose config --quiet` before startup.
- Inspect container health, exit code, logs, disk availability, volume mounts, and Docker Desktop/daemon health.
- Rebuild application images after dependency/lock changes.
- Do not delete named volumes as diagnosis; `make clean` is destructive to local state.
- For restart loops, inspect startup validation and dependency ordering instead of increasing restart counts.

## Startup failures

- Validate required environment variables without printing values.
- Check PostgreSQL reachability and migration status.
- Inspect `application.startup_completed` absence and the captured startup exception.
- Confirm installed lockfile matches `pyproject.toml`.
- Roll back configuration or image only when compatible; otherwise correct and redeploy.

## Slow requests or queries

- Use route-template histograms and `http.slow_request`; never aggregate on raw paths.
- Correlate with pool wait, query duration/operation, dependency latency, CPU, memory, and network.
- Capture a safe query plan in a protected environment; logs intentionally omit SQL.
- Optimize query/index/transaction scope before increasing timeouts or replicas.

## Recovery validation

After any dependency recovery:

- `/health/live`, `/health/startup`, and `/health/ready` return healthy states;
- metrics scrape succeeds and the alert clears after its `for` period;
- Swagger remains available only in approved nonproduction environments;
- no error/latency/restart regression remains;
- queue/backlog and dependency saturation return to normal;
- incident actions, residual risk, and follow-up owners are recorded.
