# Development Performance Baseline

## Status

These Phase 1.5 values are expected development targets for a warm Docker Desktop or Linux workstation with at least 4 available CPU cores, 8 GiB memory assigned to containers, SSD storage, and no competing heavy workload. They are not production SLO evidence.

| Measurement | Expected development target |
|---|---:|
| Cold full-stack startup after images exist | ≤ 90 seconds |
| Warm full-stack restart with healthy volumes | ≤ 45 seconds |
| Backend process startup after dependencies are healthy | ≤ 5 seconds |
| `GET /health/live` p95 | ≤ 50 ms |
| `GET /health/startup` p95 | ≤ 50 ms |
| `GET /health/ready` p95 with healthy local dependencies | ≤ 1 second |
| PostgreSQL `SELECT 1` connection/session check p95 | ≤ 100 ms |
| `/metrics` scrape p95 | ≤ 100 ms |

The general NFR remains public non-search API p95 at most 400 ms and p99 at most 1 second under an agreed representative load. Liveness is expected to be materially faster because it performs no network checks.

## Measurement method

Record hardware/OS, Docker version/resources, commit SHA, image state, cold/warm definition, dependency volume state, sample count, concurrency, p50/p95/p99, errors, and CPU/memory/disk saturation. Run the example load tests in `tests/load/` only against approved nonproduction targets.

Readiness intentionally checks five dependencies concurrently and is not a high-volume application endpoint. Load balancers should use a reasonable interval with jitter; external synthetic monitoring should prefer user-facing routes once they exist.

## Phase 1.5 verification snapshot

The 2026-07-30 Docker Desktop smoke verification returned `200` for liveness, startup, readiness, and metrics. One warm readiness sample reported PostgreSQL 57.820 ms, RabbitMQ 52.197 ms, Redis 57.215 ms, Meilisearch 66.079 ms, and MinIO 44.071 ms. These single-sample timings confirm probe function only; they are not percentile measurements or capacity evidence.

The bounded k6 and Locust examples in `tests/load/` remain intentionally manual. Establish the first repeatable p50/p95/p99 baseline in the approved staging environment after production-like resource limits and telemetry storage are selected.

## Regression policy

A regression over these targets triggers diagnosis before changing thresholds. Investigate image/dependency downloads, DNS, health timeout, database pool wait, slow queries, container throttling, logging volume, exporter backpressure, and host resource pressure. Update targets only with reviewed evidence and explain environmental changes.
