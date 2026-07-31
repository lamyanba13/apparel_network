# Phase 3.3 Store Staff Management

## Scope

Phase 3.3 adds Store membership and staff lifecycle management inside the
existing Store bounded context. It implements invitations, owner-scoped
membership visibility and maintenance, invitee acceptance or decline,
suspension, reactivation, removal, persistence constraints, audit events,
metrics, and a reviewed migration.

Identity remains frozen. This phase consumes only Identity's stable user lookup,
authenticated-principal, and permission interfaces. It does not add global
roles, permission evaluation rules, authentication behavior, ownership
transfer, media, catalog, inventory, reservations, search, notifications,
analytics, payments, or orders.

## Architecture

Store membership is a Store subdomain in the modular monolith:

```text
Store Membership API
    -> StoreMembershipService
        -> StoreInvitationService
        -> MembershipLifecycleService
        -> MembershipAuditService
        -> StoreRepository
        -> StoreMembershipRepository
        -> Identity UserRepository (stable lookup port)
            -> one PostgreSQL transaction
```

The API dependency owns transaction completion. Repositories flush but never
commit. An exception rolls back owner initialization, invitation, and state
mutations. Event publication occurs inside the use-case boundary; Prometheus
instruments remain operational telemetry rather than transactional state.

`StoreMembershipService` owns Store and membership resource boundaries.
`StoreInvitationService` validates invitation targets and duplicates.
`MembershipLifecycleService` owns conditional state transitions.
`MembershipAuditService` creates safe typed domain events. SQLAlchemy adapters
perform persistence and optimistic conditional updates.

## Persistence model

The `store_memberships` table retains membership and invitation history:

| Field | Rule |
|---|---|
| `id` | Application-generated UUIDv7 primary key |
| `store_id` | Required Store reference with restrictive deletion |
| `user_id` | Required Identity user reference with restrictive deletion |
| `role` | `owner`, `manager`, or `staff` |
| `status` | `pending`, `active`, `declined`, `suspended`, `removed`, or `expired` |
| `invited_by_id` | Required Identity actor reference |
| `invitation_expires_at` | Required only while pending; invitations last seven days |
| `accepted_at` | Required for active and suspended membership |
| `removed_at` | Required for declined, removed, and expired terminal records |
| `version` | Positive optimistic version, initially `1` |
| `created_at`, `updated_at` | Timezone-aware server timestamps |

Owner membership is initialized from the authoritative `stores.owner_id` when
the membership subdomain is first used for a Store. It is active immediately,
cannot be invited, suspended, changed, or removed, and does not implement
ownership transfer.

PostgreSQL check constraints enforce timestamp/state consistency, owner
immutability, and positive versions. Partial unique indexes enforce:

- at most one active owner for each Store;
- no duplicate active or suspended membership for a Store and user;
- no duplicate pending invitation for a Store and user.

Additional indexes support Store lifecycle listings, user membership lookup,
and pending-invitation expiry.

## Membership workflow

```text
invite
  |
  v
pending --------------------> expired
  | accept                     (after seven days)
  +----------> active <------> suspended
  | decline        |
  v                | remove
declined           v
                 removed
```

Declined, removed, and expired records are terminal and retained for audit
history. A later invitation is allowed only after the earlier invitation is
terminal. Acceptance and decline are available only to the invited identity.
Lifecycle and role mutations use the submitted or currently loaded optimistic
version and conditional updates. Racing or stale transitions return `409`.

Role changes apply only to non-owner, non-terminal memberships. A request may
change either role or lifecycle state, not both, so each version transition is
unambiguous.

## Authorization

Phase 3.3 uses the frozen permission registry and never compares Identity role
names:

| Operation | Permission | Resource policy |
|---|---|---|
| Invite member | `store:update` | Store must be owned by the principal |
| List members | `store:view` | Store must be owned by the principal |
| Change role/status | `store:update` | Store must be owned; member must belong to it |
| Remove member | `store:delete` | Store must be owned; owner member is immutable |
| Accept invitation | `store:view` | Principal must be the invited user |
| Decline invitation | `store:view` | Principal must be the invited user |

The mappings reuse stable Store permissions so Identity remains unchanged.
Store ownership and invitee checks remain in the Store application layer.
Cross-Store or cross-user access uses non-enumerating `404` responses.

## API

All routes are under `/api/v1/stores/{store_id}/members`:

| Method and path | Success | Purpose |
|---|---:|---|
| `POST /` | `201` | Invite an existing user as staff or manager |
| `GET /` | `200` | List bounded Store membership history |
| `PATCH /{member_id}` | `200` | Change role, suspend, or reactivate |
| `DELETE /{member_id}` | `204` | Remove a non-owner membership |
| `POST /{member_id}/accept` | `200` | Accept as the invited identity |
| `POST /{member_id}/decline` | `200` | Decline as the invited identity |

List pagination is offset-based with a maximum page size of 100. Mutation
requests reject unknown fields. Acceptance, decline, and update bodies carry a
positive version. Errors use the common RFC 9457 representation. OpenAPI
documents Bearer security, permissions, descriptions, response schemas, and
error responses.

## Events and audit safety

The Store event publisher receives:

- `StoreMemberInvited`
- `StoreMemberAccepted`
- `StoreMemberDeclined`
- `StoreMemberSuspended`
- `StoreMemberReactivated`
- `StoreMemberRoleChanged`
- `StoreMemberRemoved`

Events contain UUID identifiers, role, lifecycle status, timestamp, schema
version, and optional correlation ID. They contain no email address, contact
information, credentials, tokens, IP address, or free-form user content.

## Metrics

The low-cardinality Prometheus instruments are:

- `fashion_network_store_members_total`
- `fashion_network_store_member_invitations_total`
- `fashion_network_store_member_acceptances_total`
- `fashion_network_store_member_removals_total`

The member gauge counts active and suspended membership records. Counters
record completed lifecycle operations. No Store, membership, user, email, or
role labels are used.

## Migration

Alembic revision `47f0ff7d40b8` follows Store Verification head
`0f7538229016`. It creates only `store_memberships`, its foreign keys, checks,
and six explicit indexes. It is fully reversible by dropping indexes followed
by the table. Autogeneration reports no metadata drift after upgrade.

## Verification

Automated coverage verifies:

- UUIDv7 and owner membership initialization;
- invitation creation, expiry, duplicate prevention, and pagination;
- invitee-only acceptance and decline;
- suspension, reactivation, role change, removal, and terminal states;
- optimistic stale-version rejection;
- immutable owner and cross-Store non-enumeration;
- repository counts and all explicit indexes;
- safe lifecycle events and low-cardinality metrics;
- all six OpenAPI operations and permission declarations;
- real authorization dependency invocation without role comparisons;
- ordered Alembic upgrade, downgrade, re-upgrade, and drift checks.

The standard Black, Ruff, strict MyPy, Pytest, Docker Compose, OpenAPI, and Git
whitespace gates apply before Phase 3.3 is accepted.

## Boundary for Phase 3.4

Phase 3.4 may add Store media through the Uploads boundary. It must not change
membership ownership rules, expose Identity internals, or make media state part
of membership authorization. Ownership transfer remains explicitly deferred.
