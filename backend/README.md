# Backend foundation

The backend is a Python 3.13 FastAPI modular monolith managed by Poetry.

Phase 1.5 retains the Phase 1.4 shared application framework and adds the
production operations foundation:

- SQLAlchemy 2.x typed declarative metadata;
- asyncpg engine and bounded connection pool;
- request-scoped `AsyncSession` dependency;
- rollback on failed request work and automatic session cleanup;
- lifespan startup validation and graceful pool disposal;
- process-only `GET /health/live`;
- dependency-aware `GET /health/ready` for PostgreSQL, RabbitMQ, Redis,
  Meilisearch, and MinIO/R2;
- startup-sequence `GET /health/startup`;
- Alembic autogeneration wiring with no migration revisions yet;
- reusable UUIDv7, timestamp, selective soft-delete, audit, and optimistic
  version mixins.
- request-scoped IDs, correlation, start time, client IP, user agent, and a
  deliberately empty authenticated-user placeholder;
- development-pretty and production-JSON structured logging;
- centralized RFC 9457-style validation, HTTP, database, and unexpected-error
  translation;
- CORS, trusted-host, GZip, timing, request logging, and environment-aware
  security-header middleware;
- bounded cursor/offset pagination, allowlisted sorting/filtering primitives,
  response models, validators, common types, and narrowly named utilities;
- an empty `/api/v1` router plus customized development OpenAPI;
- Prometheus HTTP, status, latency, dependency, query, database-pool, and
  worker-placeholder metrics at private `GET /metrics`;
- environment-controlled OpenTelemetry instrumentation for FastAPI,
  SQLAlchemy, HTTPX, and Celery/RabbitMQ;
- disabled-by-default, PII-scrubbed Sentry for unhandled API, startup, and
  worker failures;
- slow request/query and startup/shutdown timing diagnostics;
- an injected, disabled-by-default rate-limiter port with public/store/admin
  policy scopes;
- validated idempotency keys, canonical request fingerprints, and a future
  authoritative storage port;
- opt-in ETag conditional requests and endpoint deprecation/sunset helpers;
- Brotli response compression with standards-aware GZip fallback.

No business models, business tables, authentication, users, stores, products,
inventory, or reservations are implemented.

From this directory:

```text
poetry install
poetry run alembic upgrade head
poetry run alembic check
poetry run uvicorn app.main:app --reload
```

The normal repository workflow runs these commands through Docker Compose; see
the root `README.md`.
