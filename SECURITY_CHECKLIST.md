# Phase 1.5 Security Checklist

This checklist is the operational security gate for the Fashion Network platform foundation. It complements `docs/10-security-standards.md`; it does not approve authentication or business modules.

## Application boundary

- [ ] CORS contains exact HTTPS origins in staging and production; wildcard origins are absent.
- [ ] Credentialed CORS is enabled only for approved first-party origins.
- [ ] trusted hosts contain exact deployment hosts; wildcard hosts are absent.
- [ ] HSTS is enabled at the production edge only after every required subdomain is HTTPS-ready.
- [ ] CSP, frame protection, `nosniff`, referrer policy, and permissions policy are verified from the external edge.
- [ ] request body, header, connection, and timeout limits are enforced at the edge and application.
- [ ] `/metrics`, management UIs, Swagger in production, and dependency ports are not publicly reachable.
- [ ] liveness does not check dependencies and cannot create restart storms during a shared outage.
- [ ] readiness returns only dependency names, health states, and timings—never endpoints, credentials, SQL, or provider errors.

## Secrets and configuration

- [ ] no real secret exists in Git history, images, logs, documentation, frontend bundles, or CI artifacts.
- [ ] production secrets come from the selected secret manager, not `.env.production`.
- [ ] development, staging, and production use separate credentials, RabbitMQ virtual hosts, buckets, databases, and projects.
- [ ] API, worker, migration, backup, and deployment identities have least privilege.
- [ ] every secret has an owner, consumers, rotation procedure, emergency revocation procedure, and review date.
- [ ] Sentry is disabled unless a valid environment-specific DSN is supplied.
- [ ] Sentry request bodies, cookies, authorization headers, and default PII collection remain disabled.
- [ ] OpenTelemetry exporters use encrypted authenticated transport outside private local development.

## Containers and networks

- [ ] production images use immutable digests and are rebuilt for base-image security updates.
- [ ] application containers run as non-root with no unnecessary Linux capabilities or privileged mode.
- [ ] writable paths are explicit; a read-only root filesystem is used where the runtime permits.
- [ ] PostgreSQL, Redis, RabbitMQ, Meilisearch, metrics, tracing, and management endpoints use private networks.
- [ ] local published ports bind only to `127.0.0.1`.
- [ ] container CPU, memory, process, and file-descriptor limits are configured and monitored.
- [ ] images and filesystems pass Trivy policy; SBOMs are retained with release artifacts.

## Stateful dependencies

- [ ] PostgreSQL runtime and migration roles are separate; runtime does not own the schema.
- [ ] database TLS and certificate verification are enabled outside local development.
- [ ] Redis requires authentication/TLS and contains only cache, session, rate-limit, temporary-lock, and ephemeral coordination state.
- [ ] RabbitMQ is the only Celery broker; guest/default credentials are disabled; TLS and private management access are enforced.
- [ ] Meilisearch master/admin keys remain server-side and its index contains public allowlisted fields only.
- [ ] R2/MinIO buckets are private by default and credentials are action/bucket scoped.

## Software supply chain

- [ ] Poetry and pnpm lock files are current and reviewed.
- [ ] `pip-audit` and `pnpm audit --audit-level high` pass or have a time-bound approved exception.
- [ ] CodeQL completes for Python and JavaScript/TypeScript.
- [ ] container scans have no exploitable unaccepted Critical or High finding.
- [ ] GitHub Actions use supported versions and least-privilege permissions.
- [ ] dependency and image updates are reviewed at least monthly; emergency advisories are handled immediately.

## Production evidence

- [ ] external TLS, header, CORS, host, network exposure, and secret scans pass.
- [ ] backup restoration and disaster-recovery exercises pass.
- [ ] alerts route to a named primary and backup owner and link to `docs/runbook.md`.
- [ ] penetration testing and Phase 2 threat models are complete before authentication is exposed.
- [ ] exceptions identify risk, mitigation, approver, owner, expiry, and remediation issue.

Sign-off requires Platform, Security, and Backend owners. An unchecked item is not implicitly accepted.
