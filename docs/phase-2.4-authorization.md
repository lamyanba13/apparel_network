# Phase 2.4 Authorization

## Status and scope

Phase 2.4 establishes Identity-owned, database-driven role-based access
control without adding business-module behavior. Authentication, JWT claims,
refresh rotation, session lifecycle, and the frozen platform foundation remain
unchanged.

The authorization layer supplies candidate permissions. It does not decide
store membership, tenant ownership, resource state, or other business rules.
Those decisions belong to policies implemented by the module that owns the
resource.

## Security model

Authorization uses two layers:

1. Identity resolves current roles and their candidate permissions from
   PostgreSQL.
2. The resource-owning module applies contextual policy for identity, target
   resource, ownership, membership, and lifecycle state.

Both layers must grant an operation. Missing data, missing policy
implementation, invalid identifiers, and resolution failures deny access.
Endpoints never compare role strings directly and business modules never query
Identity permission tables.

Access JWTs remain identity-only. Roles and permissions are deliberately
excluded so changes take effect without waiting for token expiry.

## Canonical identifiers

Permission names use `resource:action`, with lowercase snake-case segments.
Role names use lowercase snake case. The application registry and PostgreSQL
check constraints enforce the same rules.

The initial permission vocabulary is:

- `store:create`, `store:view`, `store:update`, `store:delete`
- `catalog:create`, `catalog:update`, `catalog:view`
- `inventory:view`, `inventory:update`
- `reservation:create`, `reservation:cancel`
- `admin:access`
- `system:manage`

The vocabulary is data, not branching logic. `PermissionName` exposes the
reviewed foundational vocabulary as typed string constants so modules do not
repeat literals. It is a compile-time convenience rather than an authorization
source: new permissions are registered in PostgreSQL and invalidation is
performed through `PermissionService`.

## Default roles

Alembic seeds immutable system roles and their initial candidate grants:

| Role | Canonical name | Initial candidate grants |
|---|---|---|
| Super Administrator | `super_admin` | All Phase 2.4 permissions |
| Administrator | `admin` | `admin:access` |
| Store Owner | `store_owner` | Store view/update, catalog create/update/view, inventory view/update |
| Store Staff | `store_staff` | Catalog update/view, inventory view/update |
| Customer | `customer` | Store/catalog/inventory view and reservation create/cancel |
| Guest | `guest` | Store/catalog/inventory view |

These grants do not confer tenant or object ownership. The Store, Catalog,
Inventory, and Reservation modules must add resource policies in their own
phases.

## Components

- `PermissionRegistry` validates canonical role and permission identifiers.
- `PermissionResolver` reads a short-lived Redis snapshot or resolves the
  authoritative PostgreSQL joins.
- `AuthorizationService` exposes `has_permission`, `require_permission`,
  `require_any_permission`, `require_all_permissions`, and `require_role`.
- `PermissionService` owns permission registration and role/permission grant
  mutation, transaction boundaries, and cache invalidation.
- `AuthorizationContext` carries the principal, resource, canonical action,
  and immutable extensible metadata through one stable policy argument.
- `PolicyDecision` records an internal allowed/denied outcome, reason, policy
  name, and optional missing permission. Client responses remain generic and
  never expose this diagnostic detail.
- `BusinessAuthorizationPolicy` defines contextual policy ports that accept an
  `AuthorizationContext` and return a `PolicyDecision`.
- `DeferredBusinessAuthorizationPolicy` denies every operation until an owning
  business module supplies its rule.
- Reusable FastAPI dependencies declare permission and role requirements
  without embedding authorization decisions in routes.

Repositories flush but never commit. Permission resolution follows:

```text
identity_user_roles
  -> identity_roles
  -> identity_role_permissions
  -> identity_permissions
  -> distinct role and permission snapshot
```

## Redis cache

Redis is an optional performance layer; PostgreSQL remains authoritative.
Snapshots have a configurable TTL:

```text
FASHION_NETWORK_AUTHORIZATION_CACHE_TTL_SECONDS=60
```

Keys use the versioned namespace
`fashion-network:identity:authorization:v1`, a global generation, and an
opaque principal UUID. A user-role change atomically advances that principal's
cache version. Permission registration and role-permission changes advance the
global generation, invalidating older snapshots without key scans. Versioning
prevents an in-flight stale resolver from repopulating the active cache key
after invalidation.

Redis read/write failure falls back to PostgreSQL resolution and never grants
access from fabricated state.

## API integration and OpenAPI

Routes may declare:

```text
require_permission("catalog:view")
require_any_permission("catalog:view", "inventory:view")
require_all_permissions("catalog:update", "inventory:update")
require_role("admin")
```

No Phase 2.4 business or administration endpoints are introduced. Protected
routes retain the bearer security requirement and generated OpenAPI operations
include an `x-authorization` description containing the declared requirement.
The application service remains the enforcement authority.

## Events, audit hooks, and metrics

Internal events:

- `AuthorizationGranted`
- `AuthorizationDenied`
- `PermissionCacheHit`
- `PermissionCacheMiss`
- `RoleAssigned`
- `RoleRevoked`
- `PermissionGranted`
- `PermissionRevoked`

Grant-change events contain canonical role/permission names, opaque affected
identity and optional actor IDs where applicable. Authorization-decision
events contain an opaque identity ID and canonical requirement. Tokens,
credentials, IP addresses, email addresses, resource contents, policy metadata,
and permission snapshots are not logged.

Prometheus counters:

- `fashion_network_identity_authorization_checks_total`
- `fashion_network_identity_authorization_denied_total`
- `fashion_network_identity_permission_cache_hits_total`
- `fashion_network_identity_permission_cache_misses_total`

The counters have no labels, preventing high-cardinality identity data.

## Validation and follow-on work

Phase 2.4 tests cover seed data, assignment and revocation, effective
permission resolution, cache hit/miss and invalidation, all authorization
service decisions, canonical identifier validation, deny-by-default policies,
structured policy decisions and immutable contexts, grant-change events,
metrics exposure, OpenAPI metadata, Alembic drift, and the unchanged identity
persistence layer.

Phase 2.5 may implement account-security controls. MFA, OAuth, SSO, passkeys,
store ownership, membership policy, and business authorization remain outside
Phase 2.4.
