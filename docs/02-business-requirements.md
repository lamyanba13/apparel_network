# Business Requirements

## Purpose

This document defines the business capabilities, policies, scope, actors, and acceptance outcomes for Fashion Network. It deliberately avoids implementation details unless they constrain business correctness.

## Business actors

| Actor | Responsibility | Authority boundary |
|---|---|---|
| Customer | Discover products and request reservations. | May access public data and only their own private account and reservations. |
| Store owner | Operate a participating store and control staff access. | May act only for stores to which they have an active owner membership. |
| Store staff | Perform delegated store operations. | May act only within assigned store permissions. |
| Administrator | Operate and protect the platform. | May use only assigned administrative permissions; sensitive actions are audited. |
| Platform operator | Defines policies and operates infrastructure. | Does not take ownership of store inventory or fulfill customer purchases. |
| Participating store | Supplies product and availability information and fulfills reservations. | Remains responsible for inventory accuracy and in-store transactions. |

## Core business requirements

### BR-001 — Unified discovery

The platform MUST allow a customer to search the published inventory of all active participating stores through one interface.

**Business acceptance:** A customer can enter a query, apply supported filters, view matching products from eligible stores, and identify the store associated with each available item.

### BR-002 — Store ownership of inventory

The platform MUST preserve the participating store as the owner and operational custodian of inventory.

**Business acceptance:** Product presentation identifies the store; no workflow implies that Fashion Network owns, sells, ships, or guarantees the item.

### BR-003 — Store-controlled publication

Authorized store personnel MUST be able to create, update, publish, unpublish, and correct their catalog and inventory records.

**Business acceptance:** A store can make current eligible inventory searchable without platform engineering support, subject to moderation and data-quality rules.

### BR-004 — Availability transparency

The platform MUST communicate availability and inventory freshness without exposing sensitive exact stock counts to customers by default.

**Business acceptance:** Public experiences use clear states such as available, low availability, or unavailable and show the last relevant update where useful. Authorized store users may see exact quantities.

### BR-005 — Reservation coordination

An authenticated customer MUST be able to request a time-limited hold against currently available inventory at one store.

**Business acceptance:** The system prevents accepted active reservations from exceeding available stock, communicates expiry, and gives the store a workflow to fulfill or decline the reservation.

### BR-006 — Independent store fulfillment

The participating store MUST fulfill reservations and conduct any resulting transaction independently.

**Business acceptance:** The platform records reservation status but contains no payment, settlement, shipping, or platform-order workflow.

### BR-007 — Tenant isolation

Store data and operations MUST be isolated by store membership and permission.

**Business acceptance:** A person associated with one store cannot view or modify another store's private catalog operations, exact stock, staff, reservations, or analytics unless separately authorized.

### BR-008 — Role delegation

A store owner MUST be able to invite and remove store staff and assign approved operational permissions without sharing credentials.

**Business acceptance:** Staff actions are attributable to individual accounts, and access ends when membership is revoked.

### BR-009 — Store onboarding and status

Administrators MUST be able to review participating stores and control whether a store is active, suspended, or otherwise eligible for public discovery.

**Business acceptance:** Suspending a store removes its inventory from public discovery while preserving records needed for support and audit.

### BR-010 — Data quality and moderation

The platform MUST provide administrative controls for handling invalid, misleading, prohibited, or duplicate public content.

**Business acceptance:** Authorized administrators can review and restrict publication, record a reason, and leave an auditable trail.

### BR-011 — Customer account control

Customers MUST be able to manage their identity data and view or cancel their eligible reservations.

**Business acceptance:** A customer can access only their records, and account/privacy requests follow the approved lifecycle and retention rules.

### BR-012 — Operational communication

The platform MUST send necessary account and reservation communications and surface delivery status to operators.

**Business acceptance:** Critical state changes produce an in-app record and, where configured, a supported external notification without blocking the underlying transaction.

### BR-013 — Auditability

Security-sensitive and business-sensitive actions MUST be attributable and reviewable.

**Business acceptance:** Administrators can identify who changed store status, permissions, publication state, inventory adjustments, and reservation status, along with when and why where a reason is required.

### BR-014 — Operational insight

Store owners and administrators MUST have access to role-appropriate aggregate operational metrics.

**Business acceptance:** Store owners see only their store's measurements; administrators see platform-level measurements; customer personal data is not unnecessarily exposed.

### BR-015 — Regional usability

The initial experience MUST be suitable for customers and store operators in Manipur, including mobile web use and variable network quality.

**Business acceptance:** Core discovery and inventory workflows remain usable on supported mobile browsers and provide useful error/retry states on unreliable connections.

### BR-016 — Reconciliation and correction

The platform MUST detect and support correction of inconsistencies among authoritative inventory, active holds, reservations, public eligibility, and derived search state.

**Business acceptance:** Authorized operators can identify a mismatch, run an idempotent repair through an owned workflow, and preserve evidence of the original and corrected states without making untracked database edits.

## Business rules

### Store eligibility

- Only active stores are publicly discoverable.
- A suspended store cannot publish new inventory or accept new reservations.
- Historical records are retained according to policy when a store is deactivated.
- Store status changes require an authorized actor and an audit entry.

### Product publication

- A publicly searchable item must belong to an active store.
- It must have the minimum required product data, at least one valid variant, and at least one eligible inventory record.
- Public media must have completed validation.
- Unpublished or moderated content must not appear in search or public detail views.
- Store-specific descriptions and availability remain attributable to the publishing store.

### Inventory

- Exact on-hand quantities are private store operational data by default.
- Each inventory level maintains on-hand and reserved quantities; available quantity is `on_hand - reserved`.
- `0 <= reserved <= on_hand` is invariant. A stock adjustment that would reduce on-hand below reserved is rejected until affected reservations are resolved through approved workflows.
- Every inventory change must capture its origin and responsible actor or system process.
- Availability shown publicly is an indicator, not a contractual guarantee.

### Reservations

- The first release requires authentication to reserve.
- One reservation belongs to one customer and one store.
- A first-release reservation contains one product variant from one store. A customer creates separate reservations for other variants.
- The requested quantity must be positive and may be limited by platform policy.
- Stock is held only after the reservation is atomically accepted.
- An accepted reservation has a fixed expiry timestamp.
- A customer may cancel before fulfillment; store personnel may fulfill or decline according to allowed state transitions.
- Expired or cancelled holds release their quantities.
- Fulfillment decreases on-hand and reserved quantities by the held amount in the same transaction and records an inventory movement. Decline, cancellation, and expiry decrease reserved quantity without decreasing on-hand.
- Repeated attempts must not create duplicate reservations when the same idempotency key is used.
- The initial expiry duration is two hours, the maximum requested quantity is five units, and a customer may have at most five active reservations. These are validated operator-configurable policies, not hard-coded constants.

### Privacy and analytics

- Only data necessary for platform operation and approved analysis is collected.
- Store owners must not receive another store's private performance or inventory information.
- Product analytics should use pseudonymous identifiers and consent controls as required.
- Security and audit events are not repurposed for marketing.

## Business process summaries

### Store onboarding

1. A store owner supplies the required store information.
2. The platform records the store as pending review.
3. An administrator reviews the submission and records a decision.
4. On approval, the owner can configure staff, catalog, and inventory.
5. Only an active, sufficiently configured store becomes publicly discoverable.

### Inventory publication

1. Authorized personnel create or select product and variant information.
2. They record store-specific inventory.
3. The system validates required data and persists it.
4. A background projection updates search.
5. Public results reflect the update within the search-freshness objective.

### Customer reservation

1. A customer selects an available variant at one store.
2. The backend verifies identity, store eligibility, policy limits, and available quantity.
3. The backend atomically records the reservation and hold.
4. The customer and store receive the reservation details and expiry.
5. The store fulfills or declines it, the customer cancels it, or the system expires it.
6. The hold is consumed on fulfillment or released on decline, cancellation, or expiry.

## Baseline launch policies

These decisions remove implementation ambiguity while remaining changeable through governed configuration or taxonomy:

- A publishable product requires name, controlled category, description, at least one variant, at least one verified image, and current inventory. Brand is optional. Each variant requires the approved applicable size/color attributes and a store-unique reference.
- The initial user interface language is English. User-facing strings are externalizable and store-entered names/descriptions remain as submitted subject to validation/moderation.
- A new reservation becomes active immediately after the atomic stock hold succeeds. It holds one variant for two hours, permits up to five units subject to availability, and each customer may have five active reservations.
- Public availability uses `available`, `low_availability`, and `unavailable`. “Low” means available quantity is at or below an operator policy initially set to two. Public views show the inventory confirmation timestamp.
- Store onboarding requires store name, physical address in Manipur, owner identity/contact verification, public contact details, and owner attestation that submitted inventory is controlled by the store. An administrator records approval or rejection with a reason.
- Launch notifications are in-app plus email for account security and reservation state changes. SMS, push, and marketing notifications are out of scope.
- Bulk inventory import is P1 after the controlled pilot; manual dashboard maintenance is the MVP workflow.
- Suspending a store immediately blocks new publication and reservations. Existing active reservations are cancelled by an idempotent background operation, their holds are released, both parties are notified, and failures appear in an admin reconciliation queue.
- Legal retention periods and final customer-facing policy text are supplied by the authorized legal/privacy owner before production. Engineering implements configurable retention workflows and must not invent statutory claims.

## Record lifecycle policy

- Store, product, variant, membership, and user records use explicit lifecycle states when history or references must remain; a generic “soft delete everything” behavior is prohibited.
- A privacy deletion request removes or irreversibly anonymizes personal fields not subject to an approved retention need while preserving non-identifying integrity and audit references.
- Audit events, inventory movements, reservation transitions, and integration events are append-only records with policy-controlled retention.
- Physical deletion is reserved for unreferenced drafts, expired technical records, verified orphan uploads, and retention jobs that prove referential safety.
- All business timestamps use UTC; user-facing display applies the intended local timezone.

## Business acceptance for launch

Launch approval requires evidence that:

- an approved store can publish inventory and an unapproved store cannot;
- customers can discover products across multiple stores;
- no private store data crosses tenant boundaries;
- concurrent reservations cannot oversubscribe stock;
- reservation holds release correctly for every terminal path;
- suspended or unpublished content disappears from public discovery;
- critical actions are auditable;
- the platform contains no checkout, payment, logistics, or platform-fulfillment behavior.
