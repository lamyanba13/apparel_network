# Observability

## Purpose and architecture

Phase 1.5 provides vendor-neutral diagnostics for the FastAPI modular monolith and its infrastructure. It does not add business metrics.

```text
FastAPI / Celery
  |-- structured stdout logs --> managed centralized log platform
  |-- OpenTelemetry traces ----> OTLP collector --> selected managed trace backend
  |-- /metrics -----------------> managed Prometheus-compatible backend
  |-- unhandled failures -------> Sentry
                                              |
                                    Grafana-compatible dashboards
                                              |
                                    owned alerts -> runbook
```

Local development can run an optional OpenTelemetry Collector, Prometheus, and Grafana with `docker compose --profile observability up`. The collector uses a debug exporter, so no external account is required. Production uses managed telemetry storage; the local profile is not a production monitoring stack.

## Logging

Logs are structured JSON in production and readable structured lines locally. Every record includes UTC timestamp, severity, module, environment, application version, request ID, and correlation ID. HTTP completion records include method, route path, status, and duration. Requests exceeding `FASHION_NETWORK_SLOW_REQUEST_THRESHOLD_MS` emit `http.slow_request` at warning level.

SQL statements exceeding `FASHION_NETWORK_SLOW_QUERY_THRESHOLD_MS` emit `database.slow_query` with duration and operation only. SQL text, bind values, credentials, request/response bodies, cookies, authorization headers, signed URLs, customer contact data, and exact private inventory are excluded.

Logs must be retained according to the approved data-retention schedule and access-controlled as Internal or Confidential depending on their identifiers.

## Metrics

`GET /metrics` exposes Prometheus text format when `FASHION_NETWORK_METRICS_ENABLED=true`. It is excluded from OpenAPI and must remain private. The local Nginx gateway returns `404` for `/metrics`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `fashion_network_http_requests_total` | Counter | method, route template, status code | Completed HTTP requests and status distribution. |
| `fashion_network_http_request_duration_seconds` | Histogram | method, route template | Request latency/duration distribution. |
| `fashion_network_dependency_up` | Gauge | dependency | Latest readiness result for PostgreSQL, RabbitMQ, Redis, Meilisearch, and MinIO/R2 adapter endpoint. |
| `fashion_network_dependency_check_duration_seconds` | Histogram | dependency | Readiness-check latency. |
| `fashion_network_database_pool_size` | Gauge | none | Configured SQLAlchemy base pool size. |
| `fashion_network_database_pool_checked_in` | Gauge | none | Idle pooled connections. |
| `fashion_network_database_pool_checked_out` | Gauge | none | Connections currently in use. |
| `fashion_network_database_pool_overflow` | Gauge | none | Current overflow connections. |
| `fashion_network_database_query_duration_seconds` | Histogram | SQL operation | Query duration without statement text or bind values. |
| `fashion_network_worker_up` | Gauge | none | Phase 1.5 placeholder for a worker exporter. |
| `fashion_network_worker_active_tasks` | Gauge | none | Phase 1.5 active-task placeholder. |
| `fashion_network_authentication_succeeded_total` | Counter | none | Successful login operations. |
| `fashion_network_authentication_failed_total` | Counter | none | Failed login operations using the generic outcome. |
| `fashion_network_authentication_refresh_total` | Counter | none | Successful refresh-token rotations. |
| `fashion_network_authentication_refresh_reuse_total` | Counter | none | Detected reuse of revoked refresh credentials. |
| `fashion_network_authentication_logout_total` | Counter | none | Completed logout and logout-all operations. |

Route labels use FastAPI route templates or `unmatched`, never raw URLs. User, store, product, reservation, query text, request ID, and object identifiers are prohibited metric labels.

RabbitMQ queue depth/age, consumer count, unacknowledged messages, redeliveries, dead letters, confirms, and node alarms should come from the managed RabbitMQ exporter. Redis, PostgreSQL, Meilisearch, and object-storage saturation metrics should come from their managed integrations.

## Tracing

OpenTelemetry is disabled by default. Enable it with:

```text
FASHION_NETWORK_OPENTELEMETRY_ENABLED=true
FASHION_NETWORK_OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

With no endpoint, instrumentation remains local/no-export and does not prevent startup. Instrumentation covers FastAPI, outbound HTTPX, SQLAlchemy, and Celery. Celery instrumentation is the RabbitMQ tracing foundation; RabbitMQ remains the only broker. Trace sampling is parent-based and controlled by `FASHION_NETWORK_OPENTELEMETRY_TRACE_SAMPLE_RATIO`.

Resource attributes include service name, release, and deployment environment. PII and high-cardinality business identifiers must not be added as span attributes. Production OTLP uses TLS and authenticated private connectivity.

## Sentry

Sentry is disabled by default. Enabling requires both `FASHION_NETWORK_SENTRY_ENABLED=true` and a secret-managed `FASHION_NETWORK_SENTRY_DSN`. It captures unhandled API, startup, and worker-process failures. Default PII, request bodies, cookies, and sensitive headers are disabled/scrubbed. Release and environment are attached for regression tracking.

Sentry failure never changes request or worker outcomes; structured local logs remain authoritative diagnostics.

## Dashboard recommendations

Version-controlled dashboards should cover:

- API request rate, p50/p95/p99 latency, 4xx/5xx ratios, and slow-request rate;
- liveness/readiness, dependency availability, and dependency-check latency;
- database pool usage/wait, slow query rate, CPU, I/O, locks, storage, WAL, and backups;
- RabbitMQ queue depth/oldest age, consumers, redeliveries, dead letters, disk/memory alarms;
- Redis latency, memory, connections, rejected connections, and evictions;
- Meilisearch search/update latency, task backlog, index size, memory, CPU, and disk;
- API/worker container CPU, memory, restarts, file descriptors, and throttling;
- Sentry new/regressed issues by release.

## Alerting

Alerts must indicate user impact or imminent saturation, have primary and backup owners, link to `docs/runbook.md`, and be tested. Initial rules include sustained API 5xx ratio, dependency unavailability, and database pool saturation. Production adds SLO burn-rate alerts, backup/PITR failure, queue age, RabbitMQ alarms, Redis evictions, Meilisearch backlog, container restart loops, and certificate/secret expiry.

Avoid paging on a single failed readiness check or one transient request. Warning alerts may create tickets; critical alerts page only when immediate action is required.

## Local operation

```text
docker compose --profile observability up
```

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3002`
- OTLP HTTP: `http://127.0.0.1:4318`
- Collector health: `http://127.0.0.1:13133`

Set OpenTelemetry enabled to `true` in a local uncommitted override to send traces. Do not commit personal endpoints or tokens.
