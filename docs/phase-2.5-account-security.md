# Phase 2.5 Account Security

## Scope

Phase 2.5 completes password maintenance, account recovery, email
verification, and progressive account lockout within the Identity module. It
does not add MFA, OAuth, SSO, passkeys, frontend behavior, store ownership, or
business policy. Existing access-token claims, refresh rotation, session
lifecycle, and authorization decisions are unchanged.

## Architecture

The implementation follows the existing Identity Clean Architecture boundary:

- domain policy validates password candidates and defines typed security
  events;
- application services orchestrate password, token, session, lockout, and
  cleanup repositories without committing;
- SQLAlchemy adapters provide atomic persistence operations;
- FastAPI routes translate the five approved account capabilities;
- notification ports carry a short-lived plaintext token only to a future
  delivery adapter.

PostgreSQL remains authoritative. Redis is not used for recovery or
verification token truth. No external scheduler or notification provider is
introduced.

## API contract

| Method and path | Authentication | Outcome |
|---|---|---|
| `POST /api/v1/account/password/change` | Bearer access token | Verifies the current password, changes it, records history, and revokes all other active sessions. |
| `POST /api/v1/account/password/forgot` | Public, rate limited | Returns `202` with a generic response regardless of account existence or eligibility. |
| `POST /api/v1/account/password/reset` | Public, rate limited | Consumes a valid single-use reset token, changes the password, records history, and revokes every session. |
| `POST /api/v1/account/email/verify` | Public, rate limited | Idempotently consumes a valid verification token and marks the email verified. |
| `POST /api/v1/account/email/resend` | Public, rate limited | Returns `202` with a generic response regardless of account or verification state. |

Recovery and resend responses never disclose whether an email exists, is
active, is deleted, or is already verified. Verification gives the same empty
success response for valid, invalid, expired, consumed, and already-completed
requests. Reset tokens intentionally use one generic invalid-or-expired error.

## Password policy and history

Policy is environment-configurable and enforces:

- minimum and maximum length;
- uppercase, lowercase, number, and symbol requirements;
- a configurable forbidden-password set;
- similarity to the normalized email local part;
- no reuse of the current password or the five most recent historical hashes.

Violations return structured field errors with stable codes. Candidates are
never stored or logged. Current and historical credentials are Argon2id hashes.
Changing a password records the former hash before storing the new hash.

## Recovery and verification tokens

Tokens are independent opaque values generated from 32 cryptographically
secure random bytes. Only SHA-256 hashes are persisted. Each token has an
expiry and single-use state. Issuing a replacement invalidates outstanding
tokens for the same purpose and identity.

Plaintext exists only in the request boundary or the in-memory notification
message passed to `NotificationPublisher`. It must never appear in logs,
events, metrics, database columns, error details, or API responses.

The notification boundaries are:

- `EmailNotifier`;
- `SecurityNotifier`;
- `NotificationPublisher`.

Phase 2.5 provides interfaces only. A later notification module owns provider
selection, templates, delivery retries, and addresses.

## Progressive lockout

Failed authentication attempts remain the audit source. The default policy:

1. applies a 30-second delay lock at five recent failures;
2. applies a 15-minute short lock at ten failures;
3. doubles subsequent short locks at configurable intervals;
4. caps automatic lock duration at four hours.

All thresholds, observation windows, and durations are configurable. Locks
store `locked_until` and `lock_reason`; successful expiry clearing increments
`unlock_count`. A successful login resets the consecutive-failure window.
Expired temporal locks automatically clear before a login and through cleanup.
Automatic permanent bans are prohibited. The administrative unlock boundary
is an interface only and has no route or implementation.

## Persistence and migration

Alembic revision `c3d91e7a4b62` extends `identity_users` with:

- nullable `locked_until`;
- nullable `lock_reason`;
- non-negative `unlock_count`.

It adds a partial locked-user cleanup index and expiry cleanup indexes on
password-reset and email-verification tokens. Existing tables and data are
preserved. The migration is reversible and contains only Alembic operations.

## Cleanup and retention

`AccountSecurityCleanupService` is scheduler-agnostic. Each run:

- deletes expired password-reset tokens in a bounded batch;
- deletes expired email-verification tokens in a bounded batch;
- clears expired temporary locks in a bounded batch;
- emits per-account unlock events and one cleanup-completed event.

The default batch is 500 and is configurable. A future local scheduler, Celery
task, or cloud scheduler may invoke the port without changing cleanup logic.

## Events and metrics

Typed internal events:

- `PasswordChanged`
- `PasswordResetRequested`
- `PasswordResetCompleted`
- `EmailVerificationRequested`
- `EmailVerified`
- `AccountLocked`
- `AccountUnlocked`
- `PasswordPolicyViolation`
- `SuspiciousLoginDetected`
- `AccountSecurityCleanupCompleted`

Events contain opaque identity IDs and low-risk outcome metadata only. They
never contain passwords, hashes, tokens, email addresses, IP addresses, or
user agents.

Unlabeled Prometheus metrics:

- `fashion_network_identity_password_change_total`
- `fashion_network_identity_password_reset_total`
- `fashion_network_identity_email_verification_total`
- `fashion_network_identity_account_lockouts_total`
- `fashion_network_identity_security_events_total`
- `fashion_network_identity_account_security_cleanup_executions_total`
- `fashion_network_identity_account_security_cleanup_records_total`

## Security invariants

- Authentication always retains its generic invalid-credential response.
- JWT structure, signing, lifetime, and validation are unchanged.
- Refresh-token generation, hashing, rotation, and reuse response are
  unchanged.
- Password reset revokes all sessions; authenticated password change preserves
  only the current session.
- Repositories flush but never commit.
- Recovery paths do not reveal account state.
- No account-security secret is logged or used as a metric label.

## Follow-on boundary

Phase 2.6 may address further reviewed Identity work. MFA, OAuth, SSO,
passkeys, frontend account screens, store membership, and business modules
remain explicitly outside Phase 2.5.
