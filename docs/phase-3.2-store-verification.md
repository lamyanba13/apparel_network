# Phase 3.2 Store Verification

## Scope

Phase 3.2 completes Store onboarding submission and administrative review
inside the existing Store bounded context. It adds structured verification
metadata, a durable review lifecycle, owner and reviewer APIs, atomic Store
state synchronization, audit events, metrics, migration coverage, and
production verification.

Identity and Phase 3.1 Store CRUD remain frozen. This phase consumes only the
existing authenticated principal, `store:view`, `store:update`, and
`admin:access` permission interfaces. It does not add role comparisons,
permissions, Store staff, catalog, inventory, reservations, search, uploads,
analytics, notifications, payments, or orders.

## Architecture

Store Verification is a subdomain of the Store module, not a separately
deployed service:

```text
Store Verification API
    -> StoreVerificationService
        -> VerificationLifecycleService
            -> VerificationPolicyService
            -> VerificationAuditService
            -> StoreVerificationRepository
            -> StoreRepository
                -> PostgreSQL transaction
```

`StoreVerificationService` applies owner/resource boundaries and exposes the
approved use cases. `VerificationLifecycleService` coordinates conditional
updates to the verification record and the existing Store aggregate.
`VerificationPolicyService` owns normalization and state preconditions.
`VerificationAuditService` publishes safe typed events.

Both repositories use the same request-scoped SQLAlchemy session. They flush
but never commit. The API dependency commits only after both aggregate changes
and event publication succeed, and rolls back the entire request on failure.

## Persistence model

The `store_verifications` table stores one current verification record per
Store:

| Field | Rule |
|---|---|
| `id` | UUIDv7 primary key |
| `store_id` | Unique foreign key to `stores` |
| `submitted_by_id` | Identity UUID that last submitted/reopened |
| `reviewed_by_id` | Nullable Identity UUID assigned to review/final decision |
| `status` | `submitted`, `in_review`, `approved`, or `rejected` |
| `submitted_at` | Set on initial submission and every reopening |
| `review_started_at` | Set when review begins |
| `reviewed_at` | Set only for an approval or rejection |
| `rejection_reason` | Required only when rejected |
| `review_notes` | Private reviewer notes |
| evidence metadata | Business license, tax registration, owner identity, address proof, and additional notes |
| `version` | Positive optimistic concurrency number |
| timestamps | UTC `created_at` and `updated_at` |

Evidence fields are bounded textual references or declarations. They are not
uploaded objects, storage keys, binary content, or proof of authenticity.
At least one of the four evidence-reference fields is required to submit.

Database checks enforce lifecycle consistency between status, reviewer,
review timestamps, and rejection reason. Foreign keys use `RESTRICT` so Store
and Identity deletion cannot silently destroy the verification trail.

## Workflow

```text
draft Store
   |
   | submit
   v
submitted verification + pending_review Store
   |
   | start review
   v
in_review
   |                         |
   | approve                 | reject with reason
   v                         v
approved + active Store      rejected + draft Store
                                  |
                                  | owner resubmits
                                  v
                             submitted (same record)
```

Rules:

- an identical open submission returns the existing record without a write;
- a different payload cannot replace an open submission;
- only rejected records may reopen, preserving the verification UUID;
- review starts only from `submitted`;
- only the assigned reviewer may update in-progress review notes;
- decisions are allowed only from `in_review`;
- repeated approval or an identical rejection returns the terminal record;
- stale versions and racing Store state changes return `409`;
- approval and rejection update verification and Store state atomically.

## API contract

| Method and path | Permission | Resource policy |
|---|---|---|
| `POST /api/v1/stores/{store_id}/verification/submit` | `store:update` | Store must be owned by the principal and eligible to submit. |
| `GET /api/v1/stores/{store_id}/verification` | `store:view` | Verification is visible only through Store ownership. |
| `PATCH /api/v1/stores/{store_id}/verification/review` | `admin:access` | Starts review or updates notes for its assigned reviewer. |
| `POST /api/v1/stores/{store_id}/verification/approve` | `admin:access` | Approves an in-review record and activates the Store. |
| `POST /api/v1/stores/{store_id}/verification/reject` | `admin:access` | Requires a reason and returns the Store to draft. |

Reviewer operations require an optimistic `version`. The rejection request
also requires a bounded nonblank reason. Unknown request fields are rejected.
Errors use the platform RFC 9457 problem format. OpenAPI documents Bearer
security, permission requirements, examples, schemas, responses, and status
codes.

No general administrative review queue endpoint is added in Phase 3.2.
Reviewers operate on an identified Store. A future Admin phase may add a
paginated queue without weakening these service policies.

## Events and audit

Typed events:

- `StoreVerificationSubmitted`
- `StoreVerificationStarted`
- `StoreVerified`
- `StoreVerificationRejected`
- `StoreVerificationReopened`

Events contain UUID identifiers, lifecycle state, schema version, timestamp,
and optional correlation ID. Approval reuses the backward-compatible
Phase 3.1 `StoreVerified` event with optional verification and actor IDs.
Evidence values, notes, rejection details, contact information, and addresses
are deliberately excluded from event payloads and structured logs.

The initial event adapter writes allowlisted structured audit records. The
common event port remains compatible with a future transactional outbox or
dedicated Audit module.

## Metrics

Unlabeled Prometheus metrics:

- `fashion_network_store_verification_submitted_total`
- `fashion_network_store_verification_approved_total`
- `fashion_network_store_verification_rejected_total`
- `fashion_network_store_verification_pending_total`

The pending gauge counts `submitted` and `in_review` records. Store active and
verified gauges are refreshed in the same lifecycle operations. Metrics never
contain Store, Identity, reviewer, evidence, or location labels.

## Migration

Alembic revision `0f7538229016` follows Phase 3.1 revision
`d48004d70e46`. It creates only `store_verifications` and is reversible.

Indexes:

- `ix_store_verifications_status_submitted_at`
- partial `ix_store_verifications_pending`
- `ix_store_verifications_reviewed_by_status`
- unique `store_verifications_store_unique`

The existing `stores` and Identity schemas are unchanged. Alembic
autogeneration reports no drift after upgrade and after a downgrade/re-upgrade
exercise.

## Security and privacy

- Owner submission and reads are scoped through the existing Store ownership
  repository query; missing and cross-owner resources share `404`.
- Reviewer mutations require `admin:access`; route code never compares role
  names.
- JWTs, Identity persistence, permission seeds, sessions, and authentication
  behavior are unchanged.
- Evidence and review fields are private operational data and are never metric
  labels or event/log payloads.
- No file upload or object-storage behavior exists.
- Conditional version/status updates and database constraints fail closed.

## Compatibility

All five Phase 3.1 Store CRUD routes and response contracts remain available.
The `stores` table is not altered. The existing `StoreVerified` constructor
remains source-compatible; optional audit identifiers enrich only Phase 3.2
approval events. Phase 3.1 lifecycle services and repository operations remain
usable without Store Verification.

## Verification evidence

Tests cover:

- initial submission, owner isolation, UUIDv7, persistence, and idempotency;
- review start and assigned-reviewer note updates;
- approval, rejection, reopening, Store synchronization, and terminal
  idempotency;
- stale versions, missing evidence, premature decisions, duplicate records,
  and invalid transitions;
- repository transaction behavior, constraints, indexes, metrics, and all
  event types;
- permission dependencies, absence of role comparisons, OpenAPI security,
  RFC 9457 responses, and request examples;
- linear migration history, upgrade/downgrade, and metadata drift.

## Phase 3.3 boundary

Phase 3.3 may add Store memberships, invitations, staff roles scoped to a
Store, membership revocation, and corresponding tenant policies. It must not
move membership or ownership rules into Identity. Verification remains a
Store-owned prerequisite that staff management may consult through a stable
application interface.
