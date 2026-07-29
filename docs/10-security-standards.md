# Security Standards

## Security objectives

Security protects customer accounts, store isolation, inventory integrity, reservation correctness, administrative power, and service availability. Controls are risk-based, deny-by-default, and designed into each feature.

The security program uses OWASP ASVS Level 2 as the initial application-control baseline, the OWASP Top 10/API Security Top 10 as review aids, and provider best practices for managed services. Compliance labels do not replace threat modeling or tests.

## Security ownership

- A named security owner maintains policies, threat models, vulnerability triage, and incident coordination.
- Feature owners are responsible for security requirements and tests in their modules.
- Platform owners manage cloud access, network policy, secrets, patching, backups, and deployment controls.
- Every production service, secret, alert, and runbook has a primary and backup owner.

## Data classification

| Class | Examples | Handling |
|---|---|---|
| Public | Published store name, public product information, public availability indicator. | May be cached/distributed after publication checks. |
| Internal | Operational metrics, nonpublic taxonomy drafts, job status. | Authenticated workforce/system access only. |
| Confidential | Customer contact data, exact inventory, store staff details, reservations. | Least privilege, encrypted, masked in tools/logs, retention-controlled. |
| Restricted | Password hashes, session/refresh tokens, recovery tokens, API secrets, signing keys. | Dedicated secret/credential storage, never logged or exposed, tightly audited access. |

Every new field must have a classification, purpose, retention, and authorized audiences.

## Threat model priorities

Threat modeling is mandatory before implementing:

- registration, sign-in, recovery, and session refresh;
- store invitation and permission changes;
- any store-scoped read or write;
- reservation concurrency and idempotency;
- direct uploads and public media delivery;
- administrative support/moderation;
- search indexing of public/private fields;
- analytics and third-party data transmission.

Review threats including broken object-level authorization, credential stuffing, account enumeration, CSRF, XSS, injection, SSRF, mass assignment, malicious uploads, replay, race conditions, tenant leakage, stale search exposure, privilege escalation, queue poisoning, dependency compromise, and denial of service.

## Identity and authentication

- Use a maintained, standards-based authentication implementation; do not invent cryptography or token formats.
- Passwords have a minimum length supportive of passphrases, allow password managers/paste, and are checked against common/compromised values where feasible.
- Store passwords only with an approved adaptive hash (Argon2id preferred when supported and operationally tuned).
- Login and recovery responses resist account enumeration.
- Verification/recovery tokens are random, single-use, stored hashed when practical, audience/purpose-bound, and short-lived.
- Sessions have absolute and idle lifetimes appropriate to role.
- Refresh-token rotation/reuse detection or server-side session revocation is required.
- Password reset and suspicious security actions revoke affected sessions.
- Privileged administrator accounts require MFA before production launch unless a documented risk acceptance names a deadline and compensating controls.
- Authentication attempts and security changes are rate-limited and audited.

### JWT and refresh-token decision

The first release intentionally does not use browser JWT access tokens or OAuth-style refresh tokens. Server-managed opaque sessions provide immediate revocation, smaller browser exposure, and simpler role/membership changes for two first-party web applications. The cookie value is a rotating opaque session credential; only its hash is stored.

JWTs may be introduced only for a separately approved machine/integration boundary with issuer, audience, short expiry, key rotation, scope, revocation implications, and no reuse of the browser session credential. A third-party identity provider may replace Auth internals later through an ADR without changing Users or store membership ownership.

### Browser session protection

The first release uses server-managed opaque cookie sessions. It MUST:

- set `Secure`, `HttpOnly`, and appropriate `SameSite`;
- use host-only cookies and scope path narrowly;
- protect state-changing requests against CSRF using SameSite, verified `Origin`, and a session-bound anti-CSRF token;
- rotate identifiers on authentication and privilege changes;
- never place sensitive session material in JavaScript-readable storage.

Browser bearer tokens are not supported in the first release. A future change requires an ADR covering storage, refresh, revocation, CSRF/XSS trade-offs, audience, issuer, signing-key rotation, replay protection, and migration.

## Authorization and tenant isolation

- Authorization uses a hybrid RBAC/resource-policy model: constrained roles grant candidate permissions, while application policies verify actor status, store membership, target ownership, resource state, and action context. A role string alone never authorizes a resource.
- Backend authorization is mandatory on every nonpublic endpoint and job-triggered use case.
- Policies check action, resource, store, membership status, permissions, and user status.
- Store-owned repository methods require an explicit store scope.
- Never accept a client-supplied store ID as authority; compare it to membership and target ownership.
- List, export, count, search, and analytics endpoints require the same object/tenant checks as detail endpoints.
- Admin access uses explicit granular permissions and is audited.
- Support users may not silently impersonate customers or store staff.
- Revoked memberships and suspended users lose access within the documented revocation objective.
- Authorization tests include horizontal access between two stores and two customers, plus vertical role escalation.

## Input, output, and injection protection

- Validate type, length, range, format, enum, collection size, and semantic constraints server-side.
- Reject unknown mutation fields to reduce mass assignment.
- Parameterize SQL; never build queries from untrusted fragments.
- Map sort/filter names through allowlists.
- Escape output by context. React's default escaping remains enabled; any raw HTML requires sanitization and security review.
- Apply a strict Content Security Policy and avoid unsafe inline script where practical.
- Protect redirect targets with allowlists.
- Any outbound URL fetching requires a dedicated SSRF-safe adapter, scheme/host restrictions, DNS/IP validation, timeouts, size limits, and no access to cloud metadata/private networks.
- Error responses and GraphQL-style introspection concerns do not justify exposing internal models; this system uses constrained REST contracts.

## Upload and media security

- Allow only approved image/media types required by product scope.
- Validate declared MIME, extension, magic bytes, decoded content, dimensions, and maximum file size.
- Use server-generated random object keys under tenant/purpose namespaces; never trust filenames as paths.
- Store original filenames only as sanitized display metadata when needed.
- Upload into a private quarantine/pending state.
- Verify and, where selected, malware-scan/process media before publication.
- Re-encode supported images where feasible to remove active content and metadata.
- Prevent SVG or other active content unless a documented sanitizer and CSP strategy is approved.
- Signed upload/download URLs are short-lived and minimally scoped.
- R2 CORS lists only required origins and methods.
- Orphan cleanup cannot delete referenced objects and is idempotent.
- Media deletion follows retention, cache invalidation, and privacy policy.

## API and web controls

- TLS is mandatory; enable HSTS after domain and subdomain readiness.
- Use exact CORS origins; never combine wildcard origin with credentials.
- Apply security headers: CSP, frame-ancestors/frame protection, nosniff, referrer policy, and permissions policy appropriate to used capabilities.
- Enforce request body and header limits at edge/proxy and application.
- Rate-limit authentication, recovery, search abuse, reservations, uploads, and admin operations.
- Use idempotency protection for reservation creation.
- Keep detailed OpenAPI/admin documentation access appropriate to environment.
- Public error responses reveal no stack, SQL, dependency host, secret, or private identifier.
- Webhooks, if later approved, require signature verification, timestamp/replay checks, and idempotency.

## Reservation and inventory integrity

- PostgreSQL transactions and constraints—not Redis—protect stock.
- Acquire locks in deterministic order for multi-line reservations.
- Recompute availability inside the transaction.
- Enforce nonnegative stock and one logical effect per idempotency key.
- Use server time for expiry.
- Terminal transitions are conditional on current state and take effect once.
- Expiry workers are idempotent and safe under delay/duplication.
- Manual inventory adjustments require reason codes and actor attribution.
- Administrative correction uses module workflows and audit, never an untracked database edit.

## Secrets and key management

- No secret appears in source, image layers, build logs, frontend bundles, analytics, tickets, or documentation.
- Use environment-specific secret management and short-lived workload identity/OIDC where supported.
- Separate development, staging, and production credentials and projects.
- Grant least-privilege service identities: API, worker, deployment, backup, and CI permissions are distinct where beneficial.
- Document owner, consumers, creation, rotation interval, emergency rotation, and revocation for every secret.
- Rotate immediately after suspected exposure and review logs for use.
- Signing keys support overlap during rotation.
- Local `.env` files are ignored; commit only a placeholder variable-name template without values.
- Production and staging use the selected cloud secret manager. GitHub Actions obtains short-lived deployment identity through OIDC; long-lived cloud keys are prohibited where workload identity is supported.
- Secret-manager access, OpenTofu remote state, and break-glass credentials require MFA, least privilege, and audit. OpenTofu state is treated as Confidential because provider state can contain sensitive values even when configuration does not.

## Database and service security

- Production PostgreSQL, Redis, and Meilisearch are not publicly reachable unless a managed provider forces a secured endpoint with strict access controls.
- Require encrypted connections and verify certificates where supported.
- Use separate least-privilege runtime and migration database roles.
- The runtime role should not own the database or have unrestricted schema-alter privileges.
- Backup access is more restricted than ordinary read access and is audited.
- Redis commands/configuration are restricted according to provider capabilities; key namespaces and TTLs reduce blast radius.
- Meilisearch master/admin keys remain server-side; client browsers never receive private search keys that can access unfiltered documents.
- R2 credentials are scoped to required buckets and actions.
- RabbitMQ uses TLS, environment-specific virtual hosts, separate publisher/consumer identities where useful, no default guest access, and network-private management endpoints.

## Logging, monitoring, and privacy

Never log:

- passwords or password hashes;
- session, refresh, verification, recovery, CSRF, or signed URL tokens;
- authorization/cookie headers;
- provider credentials;
- complete request/response bodies by default;
- unnecessary customer contact data;
- exact private inventory in analytics.

Sentry scrubbing is configured both client-side and server-side. PostHog receives only tracking-plan fields, uses consent controls where required, and has a retention setting. Audit events are separate from product analytics and protected from ordinary modification.

Alert on:

- authentication anomalies and rate-limit spikes;
- repeated cross-tenant authorization denials;
- privileged role or store-status changes;
- unusual reservation conflict patterns;
- upload validation failures;
- secret/scanner findings;
- unexpected search-publication mismatch;
- audit pipeline failure.

## Audit integrity

- The Audit module is the only ordinary application path that inserts audit events.
- Runtime roles have no audit update/delete permission; administrators query through permission-scoped application APIs.
- Audit payload keys are allowlisted and sensitive before/after values are redacted or represented by safe change summaries.
- Sealed chronological batches are hashed and exported to a separate, access-restricted immutable archive. Because R2 does not automatically imply every Amazon S3 immutability feature, the selected retention mechanism must be verified against R2's actual supported capabilities or use a compliant archive provider.
- Audit archive restore and digest verification are part of quarterly recovery exercises.
- Database superuser compromise can still affect live data; independent export, provider access logs, restricted break-glass access, and alerting reduce—not eliminate—that risk.

## Secure development lifecycle

CI MUST include:

- secret scanning;
- dependency and lock-file vulnerability scanning;
- static analysis/lint/type checks;
- container and infrastructure scanning once those artifacts exist;
- tests for authorization, input validation, state transitions, and concurrency;
- migration review and production image SBOM.

Pull requests affecting Auth, Admin, permissions, uploads, reservation locking, secrets, or public data classification require a security-aware reviewer. High-risk changes include an updated threat model.

Dependency policy:

- pin versions and verify lockfile changes;
- prefer actively maintained packages;
- remove unused dependencies;
- remediate exploitable critical/high findings before release or document a time-bound exception;
- rebuild images regularly for base-image patches.

## Vulnerability handling

- Provide a private reporting channel in the future repository security policy.
- Triage reports by exploitability, affected data/tenants, privileges, and exposure.
- Critical issues trigger incident response and emergency release procedures.
- Preserve evidence and limit access during investigation.
- Do not disclose reporter/customer details unnecessarily.
- After remediation, add regression tests and update threat models/runbooks.

Initial remediation objectives, subject to incident severity policy:

| Severity | Triage objective | Remediation objective |
|---|---:|---:|
| Critical exploitable | Same day | Immediate mitigation; permanent fix as emergency work. |
| High exploitable | 1 business day | 7 calendar days or documented containment. |
| Medium | 5 business days | 30 calendar days. |
| Low | 10 business days | Planned backlog/release. |

## Incident response

The security incident runbook must cover:

1. detection and severity assignment;
2. incident commander and communications owner;
3. containment without destroying evidence;
4. credential/key rotation and access review;
5. eradication and validated recovery;
6. customer/store/legal notification decision by authorized owners;
7. monitoring for recurrence;
8. blameless review with assigned actions.

Production access and incident actions are logged. Emergency access is time-bound and reviewed afterward.

## Pre-launch security gate

Before production launch:

- threat models are approved;
- tenant-isolation tests pass across every store/customer collection and object endpoint;
- reservation concurrency/idempotency tests pass;
- admin MFA and granular permissions are active;
- upload validation and storage policy are tested;
- secrets and production access are inventoried;
- dependency/container scans meet policy;
- external or independent penetration testing covers the public platform and dashboard;
- backup restoration is validated;
- Audit append-only database permissions and independent archive verification are validated;
- security headers, TLS, CORS, CSRF, cookies/tokens, rate limits, and log scrubbing are verified;
- incident and emergency-rotation exercises are completed.
