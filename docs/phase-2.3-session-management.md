# Phase 2.3 Session Management

## Status

Implemented on 2026-07-30. This document records the implementation contract;
it does not change the frozen modular-monolith architecture or ADR 0009.

## Boundary

Session management is an Identity application slice. PostgreSQL remains
authoritative. Access-token claims, Ed25519 verification, opaque refresh-token
rotation, and reuse detection are unchanged. The slice has no RBAC, MFA,
trusted-device policy, risk calculation, or administrative implementation.

## API contract

All routes require a valid bearer access token and scope records by the
authenticated user:

| Method | Route | Result |
|---|---|---|
| `GET` | `/api/v1/sessions` | Active, unexpired sessions with capability flags. |
| `GET` | `/api/v1/sessions/current` | The access token's authoritative session. |
| `PATCH` | `/api/v1/sessions/{session_id}` | Rename an owned, active session. |
| `DELETE` | `/api/v1/sessions/{session_id}` | Revoke an owned, active session. |
| `POST` | `/api/v1/sessions/revoke-others` | Revoke other active sessions and preserve the current session. |

Refresh hashes, token-family identifiers, raw user agents, and refresh
credentials are never returned. Missing or cross-user session identifiers
return `404`. An already revoked or concurrently revoked session returns `409`.

## Persistence and metadata

The immutable login snapshot (`device_name`, `browser`, `operating_system`,
`ip_address`, and `user_agent`) remains available to authentication and
forensics. Phase 2.3 adds mutable presentation/activity fields:

- `display_name`;
- `last_seen_at`, `last_ip`, and `last_user_agent`;
- `last_browser`, `last_operating_system`, `last_device_type`, and `platform`;
- `city`;
- `is_trusted`.

The existing nullable `risk_score`, `last_country`, and
`last_device_fingerprint` columns implement the requested risk, country, and
device-fingerprint storage without duplicate columns. `is_trusted` is data
only; it grants no privilege and bypasses no authentication control.

Responses expose `current`, `is_trusted`, `can_rename`, and `can_revoke`
directly so clients do not infer lifecycle policy. The current session cannot
be revoked through the session-management route; clients use the explicit
logout operation. `session_version` maps to the existing optimistic-lock
`version` column, which is incremented by every in-place session mutation.

## Activity tracking

The authentication dependency exposes only the authenticated session UUID to
request state. Feature-owned middleware parses normalized device metadata and
performs an atomic conditional update after authenticated requests. The
default five-minute throttle is configurable and prevents one database write
per request. Revoked and expired sessions cannot be touched.

The parser intentionally uses broad normalized categories. It does not claim
high-confidence device identification and does not generate fingerprints.

## Cleanup

`SessionCleanupService` is an invokable application service, not an external
scheduler. Each run:

1. marks expired, unrevoked sessions as revoked;
2. deletes at most the configured batch size of revoked sessions whose expiry
   is older than the configured retention period;
3. deletes lineage leaves first, preserving the restrictive parent foreign
   key and allowing ancestors to be removed in later bounded runs;
4. emits one audit event and refreshes aggregate metrics.

Defaults are a 30-day post-expiry retention period and a 500-row batch.
Scheduling is intentionally deferred to platform job orchestration.

## Audit and metrics

Structured internal events record rename, single revocation, other-session
revocation, and cleanup completion. Event payloads contain identifiers and
counts only—never credentials or token hashes.

The security-event contract includes `SessionCreated`, `SessionRenamed`,
`SessionRevoked`, `SessionExpired`, `SessionCleanupCompleted`, and
`SessionRiskUpdated`. Creation, lifecycle, expiration, and cleanup events are
published now; risk updates have a contract but no calculation or workflow.

Prometheus exports unlabeled active/revoked gauges and cleanup/revocation
counters. No email, IP address, user ID, session ID, or device value is a
metric label.

## Administrative boundary

`AdministrativeSessionService` is a protocol only. No administrator route,
authorization decision, or cross-user implementation exists in Phase 2.3.
`CleanupJob` is the scheduler-neutral execution protocol implemented by the
session cleanup service. A local scheduler, Celery task, or cloud scheduler may
invoke that boundary later without moving retention policy into scheduling
infrastructure.
