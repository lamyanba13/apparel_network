# Functional Requirements

## Purpose and conventions

This document translates business requirements into testable system behavior. Requirement identifiers are stable and MUST be referenced from API contracts, tickets, and acceptance tests. “System” includes the public frontend, dashboard, backend, workers, and supporting data stores.

Priority labels:

- **P0:** required for the first safe production release.
- **P1:** expected shortly after the core release or included if capacity permits.
- **P2:** approved future capability, not required for initial launch.

No requirement in this document introduces platform payments, delivery, shipping, or ownership of inventory.

## Auth

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-AUTH-001 | P0 | The system MUST register and authenticate supported user accounts. | Valid credentials establish a session; invalid credentials return a generic failure; authentication events are rate-limited and audited. |
| FR-AUTH-002 | P0 | The system MUST verify account contact information used for account recovery or critical communication. | Verification tokens are single-use, expire, and do not disclose whether unrelated accounts exist. |
| FR-AUTH-003 | P0 | The system MUST support secure sign-out and revocation. | Sign-out invalidates the current refresh/session credential; account-security actions can revoke all sessions. |
| FR-AUTH-004 | P0 | The system MUST support password recovery. | Recovery uses short-lived, single-use tokens and invalidates appropriate existing credentials after reset. |
| FR-AUTH-005 | P0 | The system MUST enforce role and permission checks server-side. | UI visibility never substitutes for backend authorization; denied access uses the standard error model. |
| FR-AUTH-006 | P1 | Administrators SHOULD use stronger authentication controls. | Privileged access policy, including MFA when enabled, is enforced before administrative actions. |

## Users

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-USR-001 | P0 | A user MUST view and update permitted profile fields. | Updates are validated, audited where sensitive, and visible on a subsequent read. |
| FR-USR-002 | P0 | A user MUST view their active sessions and revoke other sessions. | Revoked sessions cannot refresh or make authenticated requests after the documented propagation interval. |
| FR-USR-003 | P0 | A customer MUST view their reservation history. | Results are paginated and never contain another customer's reservation. |
| FR-USR-004 | P0 | The system MUST accept account privacy/deletion requests. | The request is tracked; legal or operational retention is applied; completion does not destroy required audit integrity. |
| FR-USR-005 | P0 | Store memberships MUST be independent from global user identity. | One account may have memberships in multiple stores; revoking one membership does not delete the account or other memberships. |

## Stores

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-STR-001 | P0 | A store owner MUST submit a store for onboarding. | Required fields are validated and the store enters the defined review state. |
| FR-STR-002 | P0 | Authorized personnel MUST maintain store profile data. | Only permitted fields are editable; public changes respect moderation rules. |
| FR-STR-003 | P0 | Store owners MUST invite, view, change, and revoke staff memberships. | Invitations expire; duplicate active memberships are prevented; permission changes take effect promptly and are audited. |
| FR-STR-004 | P0 | Customers MUST view active store profiles. | Public responses exclude private contact, membership, and operational data. |
| FR-STR-005 | P0 | Administrators MUST approve, reject, suspend, and reactivate stores with a reason. | State transitions follow policy, update discovery eligibility, and create audit entries. |
| FR-STR-006 | P1 | Store personnel SHOULD be able to view inventory freshness and operational warnings. | Dashboard identifies stale or incomplete inventory without exposing other stores' information. |

## Products

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-PRD-001 | P0 | Authorized store personnel MUST create and edit products and variants. | Required normalized fields validate; variants are unique within the relevant product; changes preserve history fields. |
| FR-PRD-002 | P0 | Authorized personnel MUST publish and unpublish eligible products. | Ineligible records return actionable validation errors; unpublishing removes public/search eligibility. |
| FR-PRD-003 | P0 | Customers MUST view a public product detail with its store, variants, public availability, media, and freshness. | Only active, published, non-moderated content appears; exact private stock is omitted. |
| FR-PRD-004 | P0 | Products MUST support controlled category and attribute values required for filtering. | Invalid taxonomy values are rejected; changes are versioned or migrated without silently corrupting filters. |
| FR-PRD-005 | P1 | Authorized personnel SHOULD duplicate their own product as a draft. | The copy has a new identity, belongs to the same store, and does not publish automatically. |

## Inventory

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-INV-001 | P0 | Authorized store personnel MUST set or adjust on-hand quantity for a variant at their store. | Quantity remains non-negative; the operation is transactional and creates an immutable stock movement record. |
| FR-INV-002 | P0 | The system MUST calculate reservable quantity consistently. | Active holds are deducted; expired/released holds are not; concurrent writes use database safeguards. |
| FR-INV-003 | P0 | Store personnel MUST view exact inventory and movement history for their store. | Reads are tenant-scoped, filterable, paginated, and show actor/source. |
| FR-INV-004 | P0 | Public clients MUST receive only policy-approved availability states. | Exact on-hand and held values are absent from public contracts. |
| FR-INV-005 | P1 | The system SHOULD support validated bulk inventory import. | A dry-run reports row errors; accepted rows are idempotent; partial-failure behavior is explicit; an import report is retained. |
| FR-INV-006 | P0 | Inventory mutations MUST trigger search-projection work after commit. | Failed indexing is retried; it cannot roll back or corrupt the authoritative inventory transaction. |
| FR-INV-007 | P0 | The system MUST enforce `0 <= reserved_quantity <= on_hand_quantity`. | Direct adjustments, reservations, fulfillment, cancellation, decline, expiry, and retries preserve the invariant under concurrency. |
| FR-INV-008 | P0 | Operators MUST be able to reconcile inventory levels, holds, and reservation state. | A dry-run identifies mismatches; repair is permission-scoped, idempotent, audited, and never silently changes terminal history. |

## Reservations

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-RES-001 | P0 | An authenticated customer MUST create a reservation for available inventory at one active store. | Validation and the stock hold occur atomically; a retry with the same idempotency key returns the original outcome. |
| FR-RES-002 | P0 | The system MUST assign a human-readable reference and an expiry timestamp. | References are non-guessable enough for display use but never authorize access; expiry is based on server time. |
| FR-RES-003 | P0 | Customers MUST view and cancel their eligible reservations. | Only the owner can access the customer view; cancellation follows the state machine and releases the hold once. |
| FR-RES-004 | P0 | Authorized store personnel MUST list and view reservations for their store. | Exact customer fields are limited to what is required for fulfillment; access is store-scoped. |
| FR-RES-005 | P0 | Authorized store personnel MUST fulfill or decline eligible reservations. | Transitions are atomic, idempotent, permission-checked, and audited. |
| FR-RES-006 | P0 | A background process MUST expire overdue active reservations. | Each reservation expires at most once logically; holds release; delayed workers remain safe and observable. |
| FR-RES-007 | P0 | The reservation state machine MUST reject invalid transitions. | Tests cover every allowed and disallowed transition and concurrent terminal actions. |
| FR-RES-008 | P0 | Reservation policy limits MUST be configurable by operators. | Changes are validated, audited, and affect new operations without editing code. |

The baseline state model is:

- creation moves directly to `active` only after the inventory hold succeeds;
- `active` may transition to `fulfilled`, `declined`, `cancelled`, or `expired`;
- terminal states cannot transition again;
- a hold exists only while the reservation is active;
- fulfillment consumes the held quantity; other terminal states release it.

The first release does not use a `pending` state. It MUST NOT create a hold that lacks a durable reservation record.

## Search

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-SRC-001 | P0 | Customers MUST search eligible inventory using free text. | Results are relevant, paginated, and contain only active stores and published eligible stock. |
| FR-SRC-002 | P0 | Customers MUST filter by approved facets such as category, store/location, size, color, and availability. | Filters are combinable and reflected in the response metadata. |
| FR-SRC-003 | P0 | Customers MUST sort by approved search-order options. | Default relevance is deterministic enough for pagination; unsupported sorts are rejected. |
| FR-SRC-004 | P0 | Search MUST tolerate configured spelling variation and synonyms. | Search configuration is version-controlled and can be tested and rolled back. |
| FR-SRC-005 | P0 | Public detail reads MUST revalidate critical eligibility against PostgreSQL. | A stale search hit cannot authorize a reservation or expose a no-longer-public record. |
| FR-SRC-006 | P0 | Operators MUST be able to rebuild the complete search index from PostgreSQL. | Rebuild supports an alias/index-swap approach, reports progress, and does not require application downtime. |
| FR-SRC-007 | P1 | The platform SHOULD capture privacy-aware search outcomes. | Query analytics excludes secrets and unnecessary personal data and supports zero-result analysis. |
| FR-SRC-008 | P0 | Search eligibility MUST be reconciled periodically against PostgreSQL. | The job reports missing, extra, stale, and forbidden-field documents and can repair them idempotently without blocking normal writes. |

## Notifications

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-NTF-001 | P0 | The system MUST create transactional notifications for defined account and reservation events. | Event-to-template mapping is explicit; duplicate job delivery does not create duplicate user-visible sends beyond policy. |
| FR-NTF-002 | P0 | Notification sending MUST occur asynchronously after the source transaction commits. | Provider outage does not fail reservation creation; retries and terminal failures are observable. |
| FR-NTF-003 | P0 | Users MUST see their in-app notifications and mark them read. | Reads are user-scoped; unread state is consistent across sessions within the cache objective. |
| FR-NTF-004 | P1 | Users SHOULD manage optional notification preferences. | Mandatory security/operational notices cannot be disabled where policy requires them. |

## Admin

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-ADM-001 | P0 | Administrators MUST access a permission-scoped operations dashboard. | Every endpoint checks explicit admin permission; ordinary admin access is not equivalent to unrestricted database access. |
| FR-ADM-002 | P0 | Administrators MUST manage store review and moderation queues. | Decisions require structured reasons and are audited. |
| FR-ADM-003 | P0 | Administrators MUST inspect relevant users, stores, products, reservations, and job/search health for support. | Sensitive fields are masked or omitted; access is logged; mutation requires a separate permission. |
| FR-ADM-004 | P0 | Administrators MUST view audit events using filters and pagination. | Audit entries are immutable to normal application roles and include actor, action, target, timestamp, correlation ID, and safe metadata. |
| FR-ADM-005 | P1 | Authorized administrators SHOULD manage approved operational policies. | Values are validated, changes audited, and secrets are never stored in policy records. |

## Audit

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-AUD-001 | P0 | The system MUST record required security and business audit events through a dedicated Audit module. | Events include actor, action, target, UTC time, correlation/causation, outcome, and allowlisted safe metadata. |
| FR-AUD-002 | P0 | Normal application roles MUST NOT update or delete audit events. | Runtime database permissions are append-only for Audit writes and permission-scoped for reads. |
| FR-AUD-003 | P0 | Privileged audit reads and exports MUST themselves be audited. | Access records identify requester, filter/scope, purpose, and result size without recursively exposing event content. |
| FR-AUD-004 | P0 | Audit integrity MUST survive primary database compromise or accidental loss within the retention objective. | Sealed batches are exported to access-restricted immutable object storage and restore verification is exercised. |

## Analytics

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-ANL-001 | P0 | The system MUST emit a governed set of product events to PostHog. | Event names and properties follow the tracking plan; sensitive values and exact inventory are excluded. |
| FR-ANL-002 | P1 | Store owners SHOULD view aggregate metrics for their own store. | Minimum aggregation/privacy rules are applied; cross-store data is absent. |
| FR-ANL-003 | P0 | Administrators MUST view core platform operational aggregates. | Definitions match the metrics catalog and can be reconciled to authoritative data where applicable. |
| FR-ANL-004 | P0 | Analytics failure MUST NOT block core workflows. | Client and server event failures degrade safely and are sampled/monitored. |

## Uploads

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-UPL-001 | P0 | Authorized users MUST request a short-lived upload authorization for approved media types. | Permission, ownership, size, MIME allowlist, and object-key namespace are enforced server-side. |
| FR-UPL-002 | P0 | The system MUST finalize an upload only after verifying the stored object. | Metadata is checked; unverified objects cannot become public product media. |
| FR-UPL-003 | P0 | The system MUST support removal of media references without exposing storage credentials. | Authorization is tenant-scoped; deletion lifecycle is auditable and safe for shared references. |
| FR-UPL-004 | P1 | Orphaned uploads SHOULD be removed after a retention window. | Cleanup is idempotent, reports metrics, and cannot delete referenced objects. |

## Cross-cutting behavior

### Validation

- Backend validation is authoritative.
- User-facing validation errors identify fields without exposing internal details.
- Identifiers, timestamps, decimal values, enums, and pagination use the API standards.

### Audit

At minimum, audit:

- sign-in security events and credential/session changes;
- store status and membership/permission changes;
- product publication/moderation;
- stock changes and bulk imports;
- reservation terminal transitions and administrative intervention;
- operational policy changes;
- sensitive administrator reads where required by policy.

### Eventual consistency

- A successful authoritative write returns after PostgreSQL commits.
- Search, notifications, analytics, and some cache effects may complete asynchronously.
- User experiences must not claim those projections are complete until confirmed.
- All consumers must be idempotent and support replay.

## Traceability

Each implementation ticket MUST cite at least one functional requirement. Each P0 requirement MUST map to:

- an owning module;
- an API or worker contract;
- unit and integration tests;
- an end-to-end acceptance scenario where it crosses user interfaces;
- relevant security and observability controls.

The OpenAPI document and versioned integration-event schemas are contract artifacts created before endpoint or consumer implementation. Requirement traceability is included in contract operation/event metadata or adjacent governed documentation.
