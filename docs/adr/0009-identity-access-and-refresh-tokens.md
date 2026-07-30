# ADR 0009: Identity access and refresh token architecture

- Date: 2026-07-30
- Status: Accepted

## Context

Fashion Network needs short-lived API authentication, immediate session
revocation, refresh replay detection, and signing-key rotation. Authorization
data changes independently from authentication and must not become stale inside
access tokens. The original foundation proposed fully opaque browser sessions;
the approved Phase 2.2 specification replaces that transport decision while
retaining PostgreSQL as the session authority.

## Decision

Access credentials are JWTs signed with Ed25519 (`EdDSA`) and expire after 15
minutes. `ES256` is the only approved fallback; symmetric JWT algorithms are
prohibited. Every token includes a `kid` and only the claims `ver=1`, `sub`,
`sid`, `jti`, `iss`, `aud`, `iat`, `nbf`, `exp`, and `type=access`. Validation
allows 30 seconds of clock skew.

Refresh credentials are opaque, cryptographically random values with at least
256 bits of entropy. PostgreSQL stores only their SHA-256 hashes. Each login
creates a token family. Each refresh locks and revokes the parent row, creates
a child row, increments the rotation count, and issues a new access/refresh
pair. Reuse of a revoked refresh credential revokes all active rows in its
family.

Session rows reserve nullable risk metadata (`risk_score`, `last_country`,
`last_asn`, and `last_device_fingerprint`) for future anomaly detection. Phase
2.2 does not calculate or act on these values.

Access validation verifies algorithm, signature, `kid`, issuer, audience,
required claims, token type, time bounds, and the current PostgreSQL session.
Roles, permissions, membership, and business data are never JWT claims.
Signing private keys come from the environment/secret manager. The current
private key signs; current and previous public keys verify during rotation.

## Alternatives considered

- Fully opaque access sessions: simpler immediate revocation, but rejected by
  the approved Phase 2.2 API-token requirement.
- JWT refresh tokens: rejected because replay lineage, revocation, and secret
  exposure are clearer with opaque credentials.
- `HS256`: rejected because every verifier would also hold signing authority.
- Roles and permissions in JWTs: rejected because they become stale and enlarge
  the credential.

## Consequences

- Every authenticated request performs or uses a bounded cache of an
  authoritative session-state check.
- Signing-key availability is required for authentication, while previous
  public keys must remain available until all tokens they signed have expired.
- Refresh rotation produces additional short-lived database rows that require
  retention cleanup in Phase 2.3.
- Authentication services emit typed internal events. The initial in-process
  consumer produces safe logs and label-free Prometheus counters; future
  consumers may add notifications or analytics without changing authentication
  decisions.
- First-party clients must keep refresh credentials in protected cookies and
  must not persist access tokens in JavaScript-readable storage.
- This ADR supersedes the no-browser-JWT transport passages in the original
  `foundation-v1` documentation; modular-monolith boundaries remain unchanged.
