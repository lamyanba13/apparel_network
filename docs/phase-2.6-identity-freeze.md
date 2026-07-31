# Phase 2.6 Identity Module Freeze

## Status

**Frozen:** 2026-07-30

**Baseline:** `foundation-v1` plus Phases 2.1 through 2.5

**Scope:** Identity hardening, verification, optimization, tests, and
documentation only.

No authentication, authorization, session, password, federation, MFA, or
business capability was added in this phase. A future behavioral or public
contract change to Identity requires security review, an ADR when architectural,
and a new roadmap phase.

## Frozen module boundary

`backend/app/modules/identity` remains a Clean Architecture feature module:

- `domain/` owns immutable security events, authorization policies, permission
  registry values, and device metadata value objects;
- `application/` owns use cases, persistence schemas, repository ports,
  security-provider ports, policy decisions, and transaction orchestration;
- `infrastructure/` owns SQLAlchemy repositories and records, Redis permission
  caching, Argon2id, JWT signing/validation, session activity middleware, and
  structured event logging;
- `api/` owns FastAPI dependency composition, Identity transport schemas, and
  the authentication, account-security, and session routers.

Dependencies point inward. Repositories flush but never commit. Application
services establish bounded transaction scopes. PostgreSQL is authoritative;
Redis contains only disposable rate-limit and authorization-cache state.
RabbitMQ is not part of synchronous Identity behavior.

## Architecture audit

- Six Identity Alembic revisions form one linear chain with one head.
- ORM metadata and the migration head have no drift.
- Router, service, repository, policy, schema, validator, event, metric, cache,
  cleanup, and notification ports were reviewed.
- Revocation, denial, and permission-removal events no longer inherit from
  semantically opposite success events.
- Session cleanup selects ordered, bounded batches and uses
  `FOR UPDATE SKIP LOCKED` before mutation.
- Redis permission-cache and rate-limiter connections owned by the application
  close during graceful shutdown.
- No cross-module business dependency, circular import, orphan migration, or
  business model exists in Identity.

## Security audit

The following invariants are frozen:

- passwords are accepted as Pydantic secrets and persisted only as Argon2id
  hashes; password history stores hashes and prevents configured reuse;
- access tokens are 15-minute JWTs with identity-only claims, a version claim,
  Ed25519/EdDSA signing by default, `kid`, issuer and audience validation, and
  bounded clock skew;
- JWT initialization rejects a signing-key type that does not match the selected
  algorithm, and validation requires the `typ: JWT` protected header;
- refresh, verification, and reset credentials are opaque random values and
  only SHA-256 hashes are stored;
- refresh rotation is single-use, detects reuse, and revokes the token family;
- authentication failures remain generic and do not disclose account state;
- progressive lockout, reset, verification, and password-change operations use
  row locking and atomic token consumption;
- rate-limit keys are SHA-256-derived and Redis-backed; emails, IP addresses,
  passwords, bearer tokens, refresh tokens, and recovery tokens are not metric
  labels or structured-log fields;
- structured audit events retain safe event IDs, occurrence timestamps,
  correlation IDs, actor/resource IDs, outcomes, and counts while the logger
  drops non-allowlisted fields;
- production OpenAPI is disabled, and development OpenAPI documents bearer
  security and RFC 9457 `application/problem+json` errors.

Signing keys and application secrets remain environment-injected and must never
be committed. Key rotation follows ADR 0009. Redis failure never grants
authorization: permission resolution falls back to PostgreSQL or denies.

## Performance audit

- Identity lookups use explicit unique or selective indexes for normalized
  email, roles, permissions, refresh-token hashes, recovery-token hashes,
  login attempts, session state/expiry, and cleanup predicates.
- Authorization queries return scalar permission sets without loading ORM
  relationship graphs; session listing is owner-scoped and ordered.
- Request-scoped database sessions use bounded pools, rollback on failure, and
  close after use. Repositories do not create engines or commit.
- Session activity persistence is throttled and uses a conditional update.
- Cleanup work is batch-limited and safe for concurrent workers.
- Authorization cache entries are versioned, TTL-bound, and invalidated after
  role or permission mutation.
- Metrics have no user, session, email, IP, or token labels.

Global session gauges require aggregate queries only after session-management
mutations or cleanup; they are not evaluated on general authenticated traffic.
Production query latency and pool pressure remain observable through the
existing SQLAlchemy and Prometheus instrumentation.

## Public API contract

Identity routes remain under `/api/v1`:

- `/auth`: login, refresh, current-session logout, and all-session logout;
- `/sessions`: list, current, rename, revoke, and revoke-other-session
  lifecycle operations;
- `/account`: password change/recovery and email verification operations.

Every protected operation declares HTTP bearer security. All documented error
responses use `ProblemDetails` and `application/problem+json`. The model requires
`type`, `title`, `status`, `code`, `detail`, `instance`, `request_id`, and
`errors`. Validation failures use the same wire format. Tags and endpoint
descriptions are part of generated OpenAPI.

## Observability contract

Identity emits low-cardinality authentication, authorization, account-security,
session, cleanup, and security counters/gauges. Internal events are published
through the event port and currently consumed by the structured logger. Each
log is correlated with request context when present and includes an event-owned
correlation identifier when explicitly supplied. Sensitive values and direct
PII are excluded.

Operations use the shared liveness, readiness, startup, metrics, tracing,
request-ID, correlation-ID, slow-query, and dependency diagnostics. Identity
does not introduce a separate health endpoint or telemetry backend.

## Operational verification

Before production deployment:

1. load the active Ed25519 private key and public verification keys from the
   approved secret manager;
2. confirm issuer, audience, `kid`, access lifetime, clock skew, refresh
   lifetime, lockout, cleanup retention, rate limits, and Redis TTLs;
3. migrate PostgreSQL to the single Alembic head and run `alembic check`;
4. verify Redis authentication/TLS and PostgreSQL TLS, least privilege, backups,
   and point-in-time recovery;
5. exercise login, rotation, reuse detection, revocation, recovery,
   verification, RBAC denial, and cleanup in staging without real credentials;
6. verify Prometheus scrape, structured security events, trace propagation,
   alert routes, and PII/token scrubbing;
7. confirm cleanup services are invoked by the approved external scheduling
   mechanism with overlapping runs tolerated.

## Recovery notes

PostgreSQL restoration recovers users, password history, RBAC assignments,
sessions, token hashes, attempts, and audit-relevant timestamps. Redis is
rebuildable and must not be restored as authoritative Identity state. After a
suspected signing-key compromise, rotate the key, remove the compromised public
key after the bounded verification window, revoke affected sessions, and follow
the security incident runbook. A database restore to an older point can revive
previously revoked sessions; therefore revoke all sessions after an
identity-affecting point-in-time restore unless incident command explicitly
approves another containment strategy.

## Freeze exit criteria

- formatting, lint, strict typing, tests, migration drift, dependency audit,
  documentation checks, and Git whitespace checks pass;
- no deferred-work marker, dead helper, duplicate validator, circular
  import, orphan migration, or sensitive log field remains;
- the Phase 2.6 validation evidence is recorded in the delivery summary;
- unresolved production blockers are zero.

Phase 3 may consume the frozen principal, permission requirements, and policy
context interfaces. It must not move Store ownership or Store domain rules into
Identity.

## Enterprise review addendum

The post-freeze boundary, public-interface, migration, and configuration
inventories are recorded in the
[Identity Enterprise Review](identity-enterprise-review.md). That review
confirms zero forbidden business-module imports while documenting the narrower
semantic coupling in the Phase 2.4 permission vocabulary and seed data. It also
records the exact stable interface allowlist, migration evidence limits,
reserved configuration inputs, and production-validation gaps. Those
qualifications supersede any unqualified claim that Identity is already a
standalone product-agnostic library.
