# Local Development Environment

## Scope

Phase 1.4 uses the complete containerized development runtime and adds the
business-neutral application framework without implementing business features.
FastAPI now provides request context, structured logging, centralized errors,
security middleware, strict environment validation, and a future `/api/v1`
composition boundary. `docker compose up` starts the two Next.js applications,
FastAPI, Celery worker, Flower, Nginx, PostgreSQL, Redis, RabbitMQ, Meilisearch,
MinIO, and Mailpit.

RabbitMQ remains the only Celery broker. Redis is limited to caching, sessions, rate limiting, temporary reservation locks, and ephemeral coordination. PostgreSQL remains authoritative, Meilisearch remains rebuildable, and MinIO is a local substitute for Cloudflare R2.

## Runtime boundaries

- `edge`: Nginx and the web applications.
- `host-access`: services with loopback-only development port bindings.
- `app`: Nginx, FastAPI, Celery, and Flower.
- `data`: application processes and stateful dependencies; marked internal.

All host-published ports bind to `127.0.0.1`. Stateful services use named volumes. Runtime services use bounded JSON-file log rotation, restart policies, and health checks.

The one-shot `minio-init` container is the deliberate exception to restart and continuous-health policies. It waits for healthy MinIO, idempotently creates the private media bucket, writes an initialization marker, and exits successfully.

## Configuration

- `.env.example` documents the full configuration contract.
- `.env.development` contains local-only defaults.
- `.env.production` contains empty secret fields and is not a production secret source.

Changing initialized PostgreSQL, RabbitMQ, Redis, or MinIO credentials requires deleting the corresponding local volume. Do not run `make clean` unless all local state may be discarded.

## Lifecycle

```text
docker compose up
docker compose run --rm backend alembic upgrade head
docker compose --profile tools run --rm verify
docker compose down
```

The `tools` profile contains only the one-shot verifier. Observability and resilience profiles remain future work under the approved roadmap.

`alembic upgrade head` is intentionally a no-op in Phase 1.4 because no
business models or migration revisions exist. It still validates that the
asyncpg migration environment can connect and execute.

Local/test logs are readable structured lines. Production selects JSON logging
and additionally requires secure service URLs, non-development credentials,
explicit trusted hosts/CORS origins, and storage/search secrets. The committed
`.env.production` remains a deliberately unusable contract until real values
are supplied through the selected secret manager.

Rate limiting and automatic ETag handling are disabled by default. Enabling
rate limiting without an injected adapter fails startup rather than silently
claiming protection. Future command endpoints opt into the idempotency-key
dependency and a PostgreSQL implementation of its storage port. Brotli is
preferred for eligible non-streaming responses when accepted by the client;
GZip remains the fallback.

## Image policy

Phase 1.2 pins stable version tags rather than mutable `latest` tags. Renovation is a reviewed infrastructure change and must pass Compose configuration, image builds, service health, and verification. Production image digests will be pinned by the protected release workflow when production deployment is introduced.

## Production differences

Local Nginx, MinIO, Mailpit, development servers, bind mounts, and development credentials are not a production deployment specification. Production uses the selected managed ingress, managed stateful services, Cloudflare R2, immutable application images, secret-manager injection, TLS, private networking, backups, and monitored deployment gates described in the approved deployment strategy.
