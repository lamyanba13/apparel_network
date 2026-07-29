# Scaling Strategy

## Principles

Fashion Network scales the modular monolith through measurement, efficient data access, stateless replicas, workload separation, and managed-state capacity. It does not adopt microservices as a default scaling technique.

Scale in this order:

1. measure the actual bottleneck and business traffic shape;
2. fix pathological queries, payloads, algorithms, media, or retry behavior;
3. add safe caching and asynchronous work;
4. scale stateless API/frontend/worker replicas;
5. scale/tune the affected stateful service;
6. partition data or workload only with evidence;
7. consider service extraction only after simpler options and an ADR.

Correctness, tenant isolation, and operability take precedence over headline throughput.

## Capacity model

Track capacity using business units:

- active stores;
- published products and variants per store;
- inventory mutations per minute;
- search requests and facet complexity;
- product detail requests;
- concurrent reservations and contention by inventory row;
- outbox events and worker tasks;
- media objects, average bytes, transformations, and egress;
- analytics events;
- database rows, storage growth, WAL/backup growth.

Forecast normal, peak, and failure-recovery load. Recovery load matters because a queue or indexing backlog can create higher throughput after an outage than normal traffic.

## Store-count evolution plan

| Stores | Expected posture | Mandatory checkpoint |
|---:|---|---|
| 100 | Single-region managed PostgreSQL, Redis, RabbitMQ, and Meilisearch; small stateless replica counts. | Pilot measurements establish actual products/store, search traffic, freshness, media, and reservation contention. |
| 1,000 | Same logical architecture with larger managed tiers, tuned pools/indexes, queue separation, and tested rebuild/restore. | This is the design target. Pass SLOs, 2× peak headroom, search rebuild, outbox recovery, and RPO/RTO exercises. |
| 10,000 | Dedicated stateful tiers, likely read replica/reporting isolation, ledger partition review, and Meilisearch HA/capacity decision. | Before crossing, prove up to 10 million projected documents or revise the forecast; price Enterprise replication/sharding versus an alternative search engine. |
| 100,000 | Potentially 100 million documents and multi-billion-row ledgers; distributed search and archival/data-placement decisions are expected. | The initial topology does not claim this capacity. Approve search migration/Enterprise network, partition/archive implementation, multi-region DR, jurisdiction, and organizational support through ADRs. |

The modular-monolith application can survive all four stages if its contracts and data ownership remain disciplined. The same database/search deployment cannot be assumed to survive all four stages unchanged.

## Performance budgets

The NFR latency and freshness objectives are budgets allocated across:

- edge/network;
- Next.js rendering and client hydration;
- backend queueing and application work;
- PostgreSQL/Redis/Meilisearch calls;
- media delivery;
- third-party calls, which should not block core workflows.

Each service dashboard shows p50/p95/p99 by route/use-case, not only global averages.

## Frontend scaling and performance

### Public frontend

- Render/cache public store and product content at the edge only with explicit bounded staleness.
- Keep search dynamic and payloads paginated.
- Optimize and responsively serve media; avoid sending originals to small devices.
- Split code by route/feature and limit client JavaScript.
- Defer PostHog and nonessential scripts without losing core behavior.
- Use ETags/revalidation for safe public reference data.
- Prevent cache keys from mixing locale, query, or eligibility representation.

### Dashboard

- Default authenticated content to private/no-store.
- Paginate inventory, movements, reservations, staff, and audit views.
- Use debounced search only as a UI behavior; backend limits still apply.
- For bulk work, upload then execute as an asynchronous operation with progress/report rather than one long request.
- Virtualize large tables only after API pagination and accessible UX are correct.

Both apps scale horizontally because persistent state lives in backend services. Sticky sessions SHOULD NOT be required.

## Backend API scaling

- Keep API replicas stateless.
- Size database connection pools across all replicas so total connections remain within PostgreSQL capacity.
- Apply request timeouts and cancellation; reject overload deliberately rather than allowing unbounded queues.
- Limit request/body size, page size, filter complexity, and concurrent expensive operations.
- Move notification, indexing, media, cleanup, import, and aggregation work to Celery after the source transaction commits.
- Use read models for expensive cross-table screens rather than loading full aggregates.
- Profile CPU and memory before scaling replicas blindly.

Autoscaling, if supported, uses a combination of CPU/memory, request concurrency/latency, and saturation. A database bottleneck is not fixed by adding unlimited API replicas.

## PostgreSQL scaling

### Stage 1 — Schema and query discipline

- Correct data types and constraints.
- Index foreign keys and measured filters/sorts.
- Use composite/partial indexes that match real query predicates.
- Eliminate N+1 queries.
- Bound every list and backfill.
- Capture slow-query statistics and query plans.
- Keep transactions short; avoid external calls while holding locks.
- Vacuum/analyze and provider maintenance are monitored.

### Stage 2 — Resource scaling and pooling

- Increase managed database compute/storage/IOPS based on saturation evidence.
- Use an approved connection pooler if connection count becomes limiting.
- Tune application pools, statement timeouts, idle transaction timeout, and worker concurrency together.

### Stage 3 — Read scaling

Read replicas MAY serve analytics or explicitly stale-tolerant public/read-model queries. They MUST NOT decide reservation availability, session revocation, current permissions, or read-after-write operations requiring the primary.

Replica routing must account for lag and provide fallback behavior. Cross-store aggregate reporting should move to replicas/materialized read models before impacting transactional workloads.

### Stage 4 — Partitioning/archival

Partition only large append-oriented tables where retention and query patterns justify it, likely audit events, inventory movements, outbox history, notification deliveries, or analytics aggregates. Partitioning products/inventory/reservations prematurely adds complexity.

Start the partition review at 50 million rows in an append-only table, when retention cannot complete within its maintenance window, or when indexes/backups breach the capacity budget—whichever occurs first. This is a review trigger, not an automatic migration.

Archive/delete according to retention policy using bounded jobs. Do not retain infinite event/job histories by accident.

### Reservation hot rows

High contention for the last units is expected and correct serialization is preferable to overselling. Optimize by:

- locking only relevant rows;
- deterministic lock order;
- short transactions;
- indexes for active holds;
- avoiding network calls in the transaction;
- limiting requested line count and quantity;
- monitoring lock wait and conflict outcomes.

Do not weaken consistency, use stale replicas, or replace the lock with Redis to improve this latency.

## Redis scaling

Redis owns cache/rate-limit/ephemeral coordination only. RabbitMQ owns Celery transport, eliminating eviction and persistence coupling between cache and task delivery.

- Set TTLs on cache and rate-limit keys.
- Set memory policy appropriate to each workload.
- Monitor memory, evictions, command latency, connections, rejected connections, and hot keys.
- Avoid unbounded values/lists.
- Cache stampede protection uses short locks or stale-while-revalidate where business-safe.
- Redis failure must not lose authoritative state.

At higher traffic, separate security-sensitive rate limiting from disposable response caches if eviction, latency, or fail-safe behavior diverges.

## Meilisearch scaling

- Choose document granularity and facet fields carefully; excessive facets increase index cost.
- Store only public search fields.
- Batch indexing tasks.
- Monitor index size, update queue, search latency, memory, CPU, and disk.
- Version ranking/settings and validate with a fixed relevance set.
- Use versioned rebuild and cutover instead of in-place destructive schema changes.
- Scale the Meilisearch node/service vertically first. At the 10,000-store gate, evaluate Enterprise replication/sharding against an alternative engine using measured relevance, rebuild, operations, license, and cost. The Search port and PostgreSQL rebuild source make this a projection migration rather than a domain rewrite.

Search queries have length, facet, sort, and pagination limits to prevent abusive expensive combinations.

## Celery scaling

Start with named workload queues:

- `critical`: reservation expiry/reconciliation and time-sensitive operational work;
- `search`: incremental projection and rebuild batches;
- `notifications`: provider delivery;
- `bulk`: imports, cleanup, media processing, aggregates.

Exact queue names are implementation decisions, but long bulk jobs must not starve time-sensitive work.

Scale workers by:

- queue depth and oldest-message age;
- task throughput and duration percentiles;
- retry/terminal-failure ratio;
- CPU/memory and downstream service capacity.

Use prefetch/concurrency settings appropriate to task duration. Backpressure prevents workers from overwhelming PostgreSQL, Meilisearch, R2, or notification providers. Every task remains idempotent.

RabbitMQ capacity signals include queue depth/age, unacknowledged count, publish confirms, consumer utilization, redeliveries, dead letters, memory/disk alarms, and node health. Celery result state is not a business status API; durable user-visible operation records live in PostgreSQL.

## R2 and media scaling

- Upload directly to R2 with signed authorization to avoid proxying bytes through API replicas.
- Enforce file and dimension limits before/after upload.
- Serve optimized formats/sizes through the approved media delivery strategy.
- Use long-lived immutable cache keys for transformed published media; change the key/version when content changes.
- Apply lifecycle rules to abandoned pending objects and versions consistent with recovery/privacy.
- Monitor stored bytes, object count, request count, transformation cost, and egress.

## Cache candidates and exclusions

Good candidates after measurement:

- public store summaries;
- taxonomy/reference values;
- selected public product details;
- non-sensitive aggregate counts with known staleness;
- safe session lookup metadata with revocation design.

Do not use cache as authority for:

- available quantity during reservation;
- current store membership/permission beyond safe revocation limits;
- reservation state transition;
- product/store public eligibility during critical mutation;
- audit durability.

Every cache has versioned keys and a safe miss path. Delete-by-pattern across huge keyspaces is avoided; version namespaces can invalidate whole shapes safely.

## Data consistency by capability

| Capability | Consistency |
|---|---|
| Inventory adjustment | Strong, PostgreSQL transaction. |
| Reservation hold/terminal transition | Strong, PostgreSQL transaction and constraints. |
| Auth/session revocation | Strong or bounded by documented short propagation. |
| Search discovery | Eventual; target freshness in NFRs. |
| Notification delivery | Eventual, at least once logical processing. |
| Product analytics | Best effort/eventual; never blocks core. |
| Store/admin aggregates | Eventual within displayed freshness. |
| Public cache | Eventual within explicit TTL/invalidation. |

The UI communicates freshness where eventual consistency affects decisions.

## Load and resilience test progression

Before pilot:

- baseline capacity profile from NFRs;
- search query mix with cold/warm cache;
- product detail and store pages with realistic media;
- inventory update burst and outbox projection;
- last-item reservation contention;
- reservation expiration backlog;
- bulk import/rebuild while serving normal traffic;
- Redis/Meilisearch/provider interruption;
- database connection saturation protections.

After launch:

- replay anonymized traffic distributions or synthetic equivalents;
- increase one bottleneck dimension at a time;
- test at least expected peak plus agreed headroom;
- retest after schema, ranking, cache, worker, or instance changes.

Tests report correctness, error rate, tail latency, resource saturation, queue/freshness lag, and cost—not only requests per second.

## Scaling triggers

| Signal | Investigate/act |
|---|---|
| Sustained API p95/SLO breach with CPU saturation | Profile; optimize; scale replicas within DB connection budget. |
| Database CPU/IO or slow-query saturation | Fix plans/indexes; tune workload; scale managed tier; consider replica for safe reads. |
| Connection pool wait/DB max connections | Reduce leaks/transaction time; tune pools; add pooler; cap replica concurrency. |
| Queue oldest age threatens freshness/expiry SLO | Diagnose downstream; scale relevant queue; apply backpressure/replay. |
| Meilisearch p95/update backlog/disk saturation | Optimize schema/query/batches; scale tier; rebuild/compact as supported. |
| Redis eviction or cache/rate-limit instability | Separate security limits from response cache, bound keys, scale memory, and correct eviction/fail-safe policy. |
| RabbitMQ backlog, redelivery, or node alarm | Diagnose consumers/downstream, apply backpressure, scale/recover broker/workers, then replay outbox/reconciliation safely. |
| Media/analytics cost per active user rises | Reduce bytes/events/retention; enforce quotas; investigate abuse. |
| A single module consumes disproportionate CPU/workers | Scale its queue/process class within the monolith before considering extraction. |

## When service extraction may be considered

Extraction is not justified by code size or fashion. An ADR must show several of:

- sustained independent scaling need that process/queue separation cannot solve;
- a hard isolation or availability requirement;
- a stable, well-owned module boundary and contract;
- database ownership that can be separated without distributed transactions;
- an owning team capable of on-call, deployment, security, and data migration;
- measured operational benefit exceeding network, consistency, observability, and cost complexity.

Inventory and Reservations are especially poor early extraction candidates because their transaction is correctness-critical. The default decision remains modular monolith.

## Cost governance

Track monthly and per-unit costs:

- per active store;
- per thousand searches;
- per published variant;
- per thousand media views/uploads;
- per thousand reservations;
- per million background tasks/analytics events.

Set provider budgets and anomaly alerts. Capacity increases include cost estimates and rollback. Optimization must not trade away security, accessibility, data durability, or accurate reservation behavior.
