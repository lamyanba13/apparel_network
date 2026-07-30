# Resource Limits

## Purpose

These are safe starting recommendations for the backend foundation, not measured capacity guarantees. Production values must be tuned from load tests and saturation metrics while preserving at least 2× measured pilot peak headroom.

| Process/service | CPU request / limit | Memory request / limit | Initial concurrency notes |
|---|---:|---:|---|
| FastAPI replica | 0.25 / 1 vCPU | 256 / 512 MiB | One Uvicorn worker per small container initially; scale replicas before excessive in-container workers. |
| Celery worker | 0.5 / 2 vCPU | 512 MiB / 1 GiB | Start concurrency at available vCPU for mixed work; use queue-specific workers later. |
| Celery scheduler | 0.1 / 0.5 vCPU | 128 / 256 MiB | Exactly one active scheduler or duplicate-safe equivalent. |
| Nginx where required | 0.1 / 0.5 vCPU | 64 / 128 MiB | Managed ingress preferred in production. |
| OpenTelemetry Collector | 0.25 / 1 vCPU | 256 / 512 MiB | Memory limiter at 256 MiB; batch exports and monitor dropped spans. |
| Prometheus local only | 0.25 / 1 vCPU | 512 MiB / 1 GiB | Seven-day local retention; managed backend in production. |
| Grafana local only | 0.1 / 0.5 vCPU | 256 / 512 MiB | Managed dashboards preferred in production. |

## PostgreSQL

- Use a managed tier with at least 2 vCPU and 4 GiB memory for staging/load validation; production sizing follows dataset and measured I/O.
- Keep 20% of provider `max_connections` reserved for administration, migrations, failover, and monitoring.
- Budget total pool capacity as `(API replicas × API pool) + (worker processes × worker pool) + migration/operations reserve`.
- Phase 1.5 defaults are pool size 5 and overflow 10 per process; production should prefer small predictable pools and an approved pooler before large replica counts.
- Set statement, lock, idle-in-transaction, and connection timeouts. Alert before storage, connections, CPU, I/O, WAL, or replication lag reaches exhaustion.

## RabbitMQ

- Start production with a managed/clustered topology sized for three durable nodes where availability requirements support it; use quorum queues for critical durable workloads where supported.
- Reserve at least 1 vCPU and 2 GiB memory per small broker node as an initial evaluation point, then size from message rate/backlog/recovery tests.
- Configure disk free and memory alarms, connection/channel limits, message size/TTL, dead-letter policy, publisher confirms, and queue-specific prefetch.
- Keep at least 2× normal-peak recovery throughput without overwhelming PostgreSQL or Meilisearch.

## Redis

Size for bounded cache/rate/session/coordination keys plus 30% headroom. Enforce TTLs and maximum value sizes. Alert on memory above 70%, evictions, latency, rejected connections, and hot keys. Separate security-sensitive limits from response caches when their failure policies diverge.

## Meilisearch and object storage

Meilisearch requires capacity testing with the representative one-million-document profile. Keep index storage and rebuild scratch headroom, and alert on memory/disk/task queue before exhaustion. R2/MinIO limits cover object bytes/count, request rate, upload size, dimensions, and egress; originals remain private.

## Runtime controls

Production containers set CPU/memory requests and limits, process/file-descriptor limits, read-only filesystems where compatible, explicit writable temporary paths, non-root users, graceful termination, and bounded request/task concurrency. An out-of-memory restart or CPU throttling event is an alert and capacity-review input, not normal autoscaling noise.
