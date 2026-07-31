# Identity Enterprise Review

## Review status

**Review date:** 2026-07-31

**Implementation baseline:** Phase 2.6 working tree

**Purpose:** make the Identity boundary, supported interfaces, migration
lineage, and configuration posture explicit before the module is version-frozen.

This document is an audit record. It does not authorize Store, Catalog,
Inventory, Reservation, Marketplace, or other business behavior inside
Identity.

## 1. Architectural boundary audit

### Source dependency result

The complete `backend/app/modules/identity` import graph was searched for
dependencies on Store, Catalog, Product, Inventory, Reservation, and
Marketplace packages.

| Forbidden dependency | Imported package references | Result |
|---|---:|---|
| Store | 0 | Pass |
| Catalog or Product | 0 | Pass |
| Inventory | 0 | Pass |
| Reservations | 0 | Pass |
| Marketplace | 0 | Pass |

Identity imports only shared application foundations and its own packages:
configuration, request context, errors, events, database abstractions,
observability, SQLAlchemy, Redis, and approved security libraries. No business
module can reach Identity through an Identity repository adapter or ORM
relationship.

The dependency direction is therefore:

```text
Future business module
        |
        v
Identity application/domain contracts
        |
        v
Shared technical foundations
```

Identity never imports a future business module.

### Semantic-coupling qualification

The package-level boundary passes, but complete product-agnostic reusability is
not yet a truthful claim. Three Phase 2.4 artifacts contain Fashion Network
business vocabulary:

- `PermissionName` declares Store, Catalog, Inventory, Reservation, Admin, and
  System permission identifiers;
- `BusinessAuthorizationPolicy` and
  `DeferredBusinessAuthorizationPolicy` name Store, Catalog, and Inventory
  operations;
- migration `f25a7c19e4d0` seeds store/customer roles, business permissions, and
  grants.

These references do not import or call business code, and every deferred policy
denies by default. They are nevertheless semantic coupling because a reusable
Identity package would accept permission/role registration from its composition
root or owning business modules.

**Freeze decision required:** retain this vocabulary as Fashion
Network-specific Identity configuration, or approve a later extraction before
claiming that Identity is independently reusable. Moving it during this review
would change the already approved Phase 2.4 public contract and migration data,
so it was not changed silently.

### Boundary conclusion

- **No forbidden package dependency:** confirmed.
- **No hidden runtime coupling:** confirmed by imports and repository
  relationships.
- **Completely product-agnostic reusable:** not confirmed because of the
  documented permission/policy/seed vocabulary.

## 2. Public interface freeze

### Stability rules

The surfaces below are the supported Identity contracts after the Phase 2.6
commit and freeze tag. Removing a name, narrowing accepted input, changing
semantics, renaming an event or metric, changing an HTTP response, or changing a
persistence constraint requires a reviewed future phase. Additive changes still
require tests and documentation.

Imported library names, underscore-prefixed helpers, concrete SQLAlchemy
models, concrete repository adapters, middleware implementations, routers, and
Redis/JWT/Argon2 adapters are implementation details unless explicitly listed
below. Their direct import by another business module is prohibited.

The Python packages do not consistently declare `__all__`. The supported
surface is therefore this documented allowlist—not every technically importable
non-underscore name. Adding explicit export manifests is recommended before
publishing Identity as a separately packaged library.

### Application services

| Area | Stable interfaces |
|---|---|
| Authentication | `AuthenticationService`, `SessionService`, `authentication_context` |
| Session lifecycle | `SessionManagementService`, `SessionCleanupService` |
| Authorization | `PermissionResolver`, `AuthorizationService`, `PermissionService` |
| Account security | `AccountLockoutService`, `AccountSecurityService`, `AccountSecurityCleanupService` |

### Application ports

| Category | Stable interfaces |
|---|---|
| Repositories | `UserRepository`, `RoleRepository`, `PermissionRepository`, `IdentityGrantRepository`, `RefreshSessionRepository`, `PasswordHistoryRepository`, `LoginAttemptRepository`, `EmailVerificationTokenRepository`, `PasswordResetTokenRepository` |
| Security providers | `PasswordService`, `TokenService`, `LoginSecurityService`, `AccountTokenService` |
| Cache | `PermissionCache` |
| Cleanup | `CleanupJob`, `AccountSecurityCleanupJob` |
| Administrative extensions | `AdministrativeSessionService`, `AdministrativeAccountSecurityService` |
| Notifications | `EmailNotifier`, `SecurityNotifier`, `NotificationPublisher` |
| Events | shared `EventPublisher` receiving Identity domain events |

Repositories never commit. Provider ports must not expose plaintext stored
credentials. Administrative interfaces are intentionally behavior-free
extension points.

### Application and domain value contracts

- Authentication values: `AccessTokenClaims`, `AuthenticationTokens`,
  `AuthenticationContext`, `AuthenticatedIdentity`.
- Authorization values: `Permission`, `PermissionRegistry`,
  `AuthorizationPrincipal`, `AuthorizationSnapshot`, `AuthorizationContext`,
  `PolicyOutcome`, `PolicyDecisionReason`, `PolicyDecision`.
- Account-security values: `PasswordViolationCode`, `PasswordViolation`,
  `PasswordPolicy`, `PasswordPolicyValidator`, `AccountNotificationKind`,
  `AccountNotification`, `AccountSecurityCleanupResult`, `LockoutPolicy`.
- Session/device values: `DeviceMetadata`, `parse_device`.
- Identity validators: `normalize_email`, `is_argon2id_hash`,
  `is_sha256_hex_digest`.

`PermissionName`, `BusinessAuthorizationPolicy`, and
`DeferredBusinessAuthorizationPolicy` remain part of the current Phase 2.4
surface, subject to the semantic-coupling freeze decision above.

### Persistence schemas

- Users: `UserCreate`, `UserRecord`.
- Roles and permissions: `RoleCreate`, `RoleRecord`, `PermissionCreate`,
  `PermissionRecord`.
- Grants: `UserRoleCreate`, `UserRoleRecord`, `RolePermissionCreate`,
  `RolePermissionRecord`.
- Sessions: `RefreshSessionCreate`, `RefreshSessionRecord`.
- Password history and attempts: `PasswordHistoryCreate`,
  `PasswordHistoryRecord`, `LoginAttemptCreate`, `LoginAttemptRecord`.
- Recovery credentials: `EmailVerificationTokenCreate`,
  `EmailVerificationTokenRecord`, `PasswordResetTokenCreate`,
  `PasswordResetTokenRecord`.

`PersistenceSchema`, `ExpiringTokenCreate`, and `ExpiringTokenRecord` are base
implementation types and are not cross-module contracts.

### HTTP schemas and dependency contracts

- Authentication: `AuthenticationRequest`, `RefreshRequest`, `TokenResponse`,
  `LogoutAllResponse`.
- Sessions: `SessionResponse`, `SessionListResponse`, `RenameSessionRequest`,
  `RevokeOthersResponse`.
- Account security: `PasswordChangeRequest`, `PasswordForgotRequest`,
  `PasswordResetRequest`, `EmailVerifyRequest`, `EmailResendRequest`,
  `GenericAcceptedResponse`.
- Injected dependencies: `AuthenticationServiceDependency`,
  `CurrentIdentity`, `OptionalIdentity`,
  `SessionManagementServiceDependency`, `AccountSecurityServiceDependency`.
- Authorization dependencies: `require_permission`, `require_role`,
  `require_any_permission`, `require_all_permissions`,
  `AuthorizationRequirement`.

The stable HTTP interface is the generated OpenAPI contract for every
`/api/v1/auth`, `/api/v1/sessions`, and `/api/v1/account` operation. RFC
9457-style `ProblemDetails`, HTTP bearer declarations, status codes, and generic
security error wording are part of that contract.

### Domain events

All event names and schema version 1 payloads are stable:

- Authentication: `AuthenticationSucceeded`, `AuthenticationFailed`,
  `RefreshRotated`, `RefreshReuseDetected`, `LogoutCompleted`.
- Sessions: `SessionCreated`, `SessionRenamed`, `SessionRevoked`,
  `OtherSessionsRevoked`, `SessionCleanupCompleted`, `SessionExpired`,
  `SessionRiskUpdated`.
- Authorization: `AuthorizationGranted`, `AuthorizationDenied`,
  `PermissionCacheHit`, `PermissionCacheMiss`, `RoleAssigned`, `RoleRevoked`,
  `PermissionGranted`, `PermissionRevoked`.
- Account security: `PasswordChanged`, `PasswordResetRequested`,
  `PasswordResetCompleted`, `EmailVerificationRequested`, `EmailVerified`,
  `AccountLocked`, `AccountUnlocked`, `PasswordPolicyViolation`,
  `SuspiciousLoginDetected`, `AccountSecurityCleanupCompleted`.

Base event classes are extension mechanics. Consumers must dispatch on concrete
events or `event_name`, never infer success from sibling-class inheritance.

### Metrics

The following Prometheus names and their zero-label cardinality are stable:

- `fashion_network_authentication_succeeded_total`
- `fashion_network_authentication_failed_total`
- `fashion_network_authentication_refresh_total`
- `fashion_network_authentication_refresh_reuse_total`
- `fashion_network_authentication_logout_total`
- `fashion_network_identity_sessions_active`
- `fashion_network_identity_sessions_revoked`
- `fashion_network_identity_session_cleanup_executions_total`
- `fashion_network_identity_session_revocations_total`
- `fashion_network_identity_authorization_checks_total`
- `fashion_network_identity_authorization_denied_total`
- `fashion_network_identity_permission_cache_hits_total`
- `fashion_network_identity_permission_cache_misses_total`
- `fashion_network_identity_password_change_total`
- `fashion_network_identity_password_reset_total`
- `fashion_network_identity_email_verification_total`
- `fashion_network_identity_account_lockouts_total`
- `fashion_network_identity_security_events_total`
- `fashion_network_identity_account_security_cleanup_executions_total`
- `fashion_network_identity_account_security_cleanup_records_total`

User, email, IP, token, session, role, and permission labels must not be added.

### Configuration

Identity consumes the stable settings families documented in `.env.example`:

- access/refresh token lifetime and verified-email requirement;
- JWT algorithm, issuer, audience, current/previous key material, and clock
  skew;
- session activity, retention, and cleanup bounds;
- authorization-cache TTL;
- password policy, history, recovery/verification lifetime, and lockout
  controls;
- authentication and shared route rate limits;
- PostgreSQL, Redis, and service-security settings.

Secret values are configuration inputs, never public return values.

## 3. Migration audit

The Alembic graph contains six unique revisions, one base, and one head:

```text
b6d38dd509e1
  -> eb3079e2bb7e
  -> a9c2cc1d183e
  -> d41f63a709b2
  -> f25a7c19e4d0
  -> c3d91e7a4b62
```

| Check | Evidence | Result |
|---|---|---|
| Linear history | every revision has exactly one predecessor; one base and one head | Pass |
| Duplicate revisions | six files and six unique revision identifiers | Pass |
| Orphan revisions | every non-base revision is reachable from the head | Pass |
| Upgrade implementation | all six files define `upgrade()` | Pass |
| Downgrade implementation | all six files define `downgrade()` | Pass |
| Model drift | post-round-trip `alembic check` reported no operations | Pass |
| Runtime downgrade execution | isolated PostgreSQL completed head → base → head | Pass |

The first isolated rollback exposed incorrect convention-expanded constraint
names in revisions `c3d91e7a4b62` and `f25a7c19e4d0`. Their downgrade operations
now mark the existing physical names with `op.f(...)`, preventing Alembic from
applying the naming convention twice. The complete round trip then passed, and
the existing Alembic test continues to verify empty-database upgrade, lineage,
head, and drift. A future CI downgrade test must provision its own disposable
database rather than risk a shared developer database. Production data rollback
still requires backup and restore planning even though DDL downgrade succeeds.

## 4. Configuration audit

### Environment coverage

`Settings` exposes 83 fields. The audit added the five missing overridable
application metadata entries to `.env.example`:

- `FASHION_NETWORK_APPLICATION_NAME`
- `FASHION_NETWORK_APPLICATION_VERSION`
- `FASHION_NETWORK_APPLICATION_DESCRIPTION`
- `FASHION_NETWORK_APPLICATION_CONTACT_NAME`
- `FASHION_NETWORK_APPLICATION_LICENSE_NAME`

All `Settings` fields now have a corresponding `.env.example` entry. The four
additional `FASHION_NETWORK_S3_*` and `FASHION_NETWORK_SMTP_*` variables are
Compose/health/notification-foundation inputs outside the current `Settings`
model and remain documented in their service sections.

### Usage classification

- Runtime-consumed settings are read through the validated `Settings` object.
- `meilisearch_master_key`, `s3_access_key_id`, and `s3_secret_access_key` are
  currently validation-only in the API process; their clients are not yet
  implemented.
- `session_cleanup_retention_days`, `session_cleanup_batch_size`, and
  `account_security_cleanup_batch_size` are reserved for the cleanup-job
  composition adapter. Cleanup services exist, but no external scheduler is
  intentionally wired.
- `api_host` and `api_port` are launcher-oriented values; the application does
  not read them after process start.

The latter groups are intentionally inert, but they are not runtime-consumed.
The repository therefore does **not** meet a literal “zero unused settings”
claim. They should either be consumed by the approved Phase 3 deployment/job
composition or removed in a separately reviewed foundation change.

### Defaults and production validation

Positive controls:

- development credentials, localhost/placeholder service URLs, missing JWT
  keys, wildcard trusted hosts, non-HTTPS browser/API/search/storage URLs, weak
  search/storage secrets, invalid algorithms, malformed URLs, invalid ports,
  and inconsistent password/lockout policies are rejected where applicable;
- Sentry requires a DSN when enabled;
- telemetry exporters, Sentry, ETags, and rate limiting are opt-in;
- access-token, clock-skew, pool, cleanup, rate, and password values are
  bounded.

Production-validation gaps:

- production does not require `rate_limit_enabled=true`;
- production does not reject `database_echo=true`;
- PostgreSQL TLS is not explicitly required by the database URL validator;
- production permits `redis://` instead of requiring `rediss://`;
- production permits `amqp://` instead of requiring `amqps://`.

These are deployment-policy gaps, not evidence of a currently committed secret.
They must be resolved or explicitly enforced at the managed-service/network
layer before production approval. Tightening them in `Settings` would change the
frozen foundation’s startup contract and needs an approved hardening change.

## Final assessment

| Concern | Result |
|---|---|
| Forbidden module imports | Pass |
| Hidden runtime business coupling | Pass |
| Product-agnostic semantic boundary | Qualification required |
| Public interface inventory | Complete in this document |
| Linear/unique/reachable migrations | Pass |
| Runtime downgrade evidence | Pass |
| Environment-variable documentation | Pass after `.env.example` update |
| Literal zero-unused-settings standard | Not met; reserved inputs documented |
| Safe production validation | Strong baseline with five documented gaps |

The Identity implementation remains suitable for Fashion Network Phase 3.
Calling it a completely reusable standalone Identity library or granting final
production configuration approval requires resolution of the explicit items
above.
