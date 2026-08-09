# Fashion Network

Fashion Network is a **digital commerce and inventory network for participating retailers in Manipur**, beginning with clothing and apparel stores.

The platform connects the physical inventory of participating stores with a shared digital discovery and commerce layer. Customers can discover products, view store availability, place orders or reservations, and receive fulfillment and commerce updates, while each retailer retains ownership and physical control of its inventory.

The platform is designed around an important principle:

> **Retailer data acquisition and platform operation are separate concerns.**

A retailer may provide its catalog and inventory data through an existing POS/retailer system, manual preparation, or platform-assisted data collection. Once that data enters the platform, all retailers use the same canonical Store, Catalog, Product, Variant, Pricing, Inventory, and Commerce model.

The `docs/` directory is the source of truth for product and technical decisions.

---

## Product mission

Fashion Network is being built to solve a simple problem in the local retail market:

**Customers often do not know which physical store currently has the product they want, while retailers have inventory that is difficult to discover outside their own physical shop, Instagram, Facebook, or existing sales channels.**

Fashion Network creates a shared digital inventory network that makes participating retailers and their products discoverable while preserving the retailer's ownership of the merchandise.

The long-term objective is to become the digital commerce infrastructure connecting local retailers, their inventory, and customers across Manipur.

---

## Product boundary

Fashion Network:

* onboards participating retailers;
* digitizes retailer catalogs;
* indexes products and store inventory;
* stores product images and merchandising information;
* allows customers to search and discover products across stores;
* provides store-specific inventory visibility;
* supports carts, checkout, orders, payments, reservations, fulfillment, returns, refunds, and promotions;
* provides retailer tools for catalog, inventory, order, shipment, and operational management;
* sends customer commerce notifications;
* provides administrators with controls to operate and monitor the network;
* maintains an auditable event and inventory history.

Fashion Network does **not** require retailers to abandon their existing sales channels.

A retailer may continue operating through:

* physical store sales;
* Instagram;
* Facebook;
* WhatsApp or other existing channels;
* POS/retailer software;
* other existing business processes.

Fashion Network becomes an additional digital infrastructure layer for participating retailers.

The retailer remains the owner of its products and physical inventory.

---

# Retailer onboarding and data acquisition

Retailers do not need to have an existing digital catalog to join the platform.

The platform supports multiple data-acquisition paths.

## Option A — Existing digital retailer

Retailers that already sell through Instagram, Facebook, POS software, spreadsheets, or another digital system may already have useful product information.

Their existing information can be transformed into the platform's canonical catalog structure.

Typical source data includes:

* product name;
* product description;
* category;
* brand;
* selling price;
* sizes;
* colors;
* SKU;
* available quantity;
* product images;
* store information.

The existence of an existing digital sales account is therefore an **onboarding advantage**, not a platform requirement.

## Option B — Offline retailer

A retailer does not need an Instagram or Facebook selling account.

Traditional physical clothing stores can be onboarded directly by collecting their catalog and inventory information.

Platform staff may assist with:

* collecting product information;
* photographing or obtaining product images;
* organizing products into categories;
* recording variants;
* recording stock;
* preparing the retailer's spreadsheet;
* validating the information before publication.

This is particularly important because a significant portion of the local apparel market operates primarily through physical stores.

## Data ingestion

During the initial rollout, retailer data is expected to enter the platform primarily through structured spreadsheets.

Supported acquisition paths are:

### 1. POS / retailer system

Retailer exports relevant product and inventory information from an existing system.

```text
POS / Retailer System
        ↓
Spreadsheet
        ↓
Validation
        ↓
Catalog / Inventory
```

### 2. Retailer manual preparation

A retailer provides information manually using the platform's spreadsheet template.

```text
Retailer
   ↓
Spreadsheet Template
   ↓
Validation
   ↓
Catalog / Inventory
```

### 3. Platform-assisted collection

Platform staff collect and prepare retailer data.

```text
Physical Store
      ↓
Platform Staff
      ↓
Product + Variant + Stock + Images
      ↓
Spreadsheet / Import Workflow
      ↓
Validation
      ↓
Catalog / Inventory
```

The third path is particularly important during the controlled launch because it reduces the amount of technical work required from retailers.

### Future integrations

Direct integrations with POS systems, retailer APIs, or automated inventory feeds may be added later.

These are **data-source integrations**, not separate commerce architectures.

Regardless of how data enters the platform, the resulting data must conform to the same canonical domain model.

---

# Product images

Product imagery is part of the catalog onboarding process.

A product record may require:

* primary product image;
* additional product images;
* variant-specific imagery where appropriate;
* store-provided imagery;
* platform-collected imagery.

Images are stored through the platform's media infrastructure and associated with the appropriate catalog entities.

Product images are therefore treated as structured catalog data rather than an optional social-media attachment.

---

# Canonical retailer model

Once a retailer is onboarded, the source of its data no longer determines how the platform operates the retailer.

All retailers use the same conceptual model:

```text
Store
  │
  ├── Catalog
  │     ├── Product
  │     │     ├── Variant
  │     │     └── Media
  │     │
  │     └── Categories / Collections
  │
  ├── Pricing
  │
  └── Inventory
        │
        ├── Available Quantity
        ├── Reserved Quantity
        ├── Stock Movements
        └── Operational Adjustments
```

The platform therefore does not maintain separate "Instagram retailer" and "offline retailer" architectures.

The difference exists only during **data acquisition and onboarding**.

---

# Commerce model

The platform has evolved beyond simple product discovery.

The commerce architecture now supports:

```text
Discovery
    ↓
Cart
    ↓
Checkout
    ↓
Order
    ↓
Payment
    ↓
Reservation
    ↓
Fulfillment
    ↓
Shipment
    ↓
Delivery
```

Supporting workflows include:

```text
Promotions
    ↓
Checkout / Order

Returns
    ↓
Refunds

Commerce Events
    ↓
Notifications
```

Retailers remain responsible for fulfilling their physical-store obligations, while the platform provides the digital coordination layer.

---

# Commerce boundaries

The platform contains dedicated bounded contexts for:

* Identity
* Stores
* Catalog
* Products
* Product Variants
* Pricing
* Inventory
* Carts
* Checkout
* Orders
* Payments
* Reservations
* Shipments
* Returns
* Refunds
* Promotions
* Notifications
* Commerce Events
* Retailer Operations

Each bounded context owns its domain behavior and persistence boundaries.

Cross-domain workflows occur through application services and defined contracts rather than direct table manipulation.

---

# Inventory ownership

Inventory remains owned by the participating retailer.

The platform maintains a digital representation of retailer inventory for discovery and commerce coordination.

The authoritative platform inventory model contains:

* product variant;
* store;
* on-hand quantity;
* reserved quantity;
* available quantity;
* inventory status;
* optimistic version;
* audit information;
* stock movement history.

Inventory mutations are performed through domain services and operational commands.

The platform does not assume that the physical store's inventory automatically changes merely because a digital record changes.

---

# Inventory synchronization model

Inventory synchronization is intentionally separated from retailer onboarding.

The initial ingestion mechanism is spreadsheet-based.

After onboarding, inventory may be maintained through:

* retailer dashboard operations;
* platform staff operations;
* spreadsheet imports;
* future POS integrations;
* future automated retailer integrations.

The objective is to progressively reduce manual work without changing the underlying inventory model.

```text
External Data Source
        ↓
   Ingestion Layer
        ↓
 Validation / Mapping
        ↓
Canonical Platform Data
        ↓
Product / Variant / Inventory
        ↓
Search + Commerce
```

The platform must never make the external source format part of the core domain model.

Phase 5.11 implements this boundary with Store-scoped CSV/XLSX jobs, staged
images, structured preview errors, and atomic canonical commit. Both retailer
exports and staff-collected packages use the same Product, Variant, Product
Media, Pricing, and Inventory services. See
[`phase-5.11-retailer-catalog-inventory-ingestion.md`](phase-5.11-retailer-catalog-inventory-ingestion.md).

---

# Inventory operational controls

Phase 5.10 introduced explicit retailer inventory operations.

Supported operations include:

* stock adjustments;
* reconciliation;
* initial stock;
* stock increases;
* stock decreases;
* damage;
* loss;
* found stock;
* corrections;
* shipment consumption;
* movement history;
* low-stock monitoring;
* out-of-stock monitoring.

Inventory movements are append-only and auditable.

Operational mutations use optimistic locking and reservation-aware inventory protection.

---

# Event architecture

Commerce domains use the shared transactional outbox.

Business mutations and their corresponding events are persisted atomically.

The event reliability architecture provides:

* durable event persistence;
* concurrent worker claiming;
* `FOR UPDATE SKIP LOCKED`;
* processing leases;
* crash recovery;
* deterministic retries;
* terminal failure handling;
* consumer receipts;
* idempotency;
* administrator recovery;
* operational metrics.

PostgreSQL remains the authoritative source of durable commerce events.

RabbitMQ/Celery provides asynchronous processing and delivery rather than replacing PostgreSQL as the source of truth.

---

# Search

Product and inventory discovery is implemented through a rebuildable search projection.

PostgreSQL remains authoritative.

Meilisearch is a derived search system and may be rebuilt from authoritative data.

Search is designed for near-real-time discovery rather than transactional correctness.

Transactional decisions such as:

* inventory availability;
* reservation;
* payment state;
* order state;

must always be validated against authoritative services and persistence.

---

# Architecture at a glance

Fashion Network is a modular monolith with three deployable applications:

* `frontend/` — public customer experience built with Next.js, React, TypeScript, and TailwindCSS.
* `dashboard/` — retailer and administrator experience using the same frontend stack.
* `backend/` — FastAPI application containing bounded contexts and asynchronous Celery workers.

Infrastructure includes:

* PostgreSQL — system of record;
* Redis — caching, rate limiting, and short-lived coordination;
* RabbitMQ — Celery broker;
* Meilisearch — rebuildable search projection;
* Cloudflare R2 — uploaded media storage;
* Celery — asynchronous processing;
* Nginx — production edge/reverse proxy.

The architecture uses Clean Architecture and bounded-context separation inside a modular monolith.

---

# Current commerce architecture

The completed commerce foundation currently includes:

### Phase 5.0

Shopping Cart

### Phase 5.1

Checkout

### Phase 5.2

Orders

### Phase 5.3

Payments

### Phase 5.4

Inventory Reservations

### Phase 5.5

Shipments and Fulfillment

### Phase 5.6

Returns and Refunds

### Phase 5.7

Promotions and Discount Engine

### Phase 5.8

Customer Notifications and Commerce Events

### Phase 5.9

Commerce Event Reliability and Operational Hardening

### Phase 5.10

Retailer Operations and Inventory Management

### Phase 5.11

Retailer Catalog and Inventory Ingestion Foundation

The Phase 5 commerce foundation is therefore considered an integrated system rather than a collection of independent modules.

---

# Current engineering baseline

The repository currently has:

* Clean Architecture boundaries;
* PostgreSQL persistence;
* production-backed integration tests;
* transactional outbox;
* durable event processing;
* optimistic locking;
* authorization and Store isolation;
* audit fields;
* soft deletion where required;
* structured metrics;
* migration integrity checks;
* containerized development and production environments;
* dependency security gates;
* frontend and backend validation;
* production-image security scanning.

The current validated baseline is **Phase 5.11**.

---

# Documentation map

The `docs/` directory is the source of truth for product and technical decisions.

The major documentation areas are:

1. Vision
2. Business Requirements
3. Functional Requirements
4. Non-functional Requirements
5. Technology Stack
6. System Architecture
7. Folder Structure
8. Coding Standards
9. API Standards
10. Security Standards
11. Deployment Strategy
12. Development Roadmap
13. Sprint Plan
14. Risk Analysis
15. Scaling Strategy
16. Contributing Guide
17. Git Workflow
18. Local Development Environment
19. Architecture Review
20. Observability
21. Platform Runbook
22. Backups
23. Disaster Recovery
24. Resource Limits
25. Performance Baseline
26. Production Deployment Checklist
27. Dependency Report
28. Architecture Decision Records
29. Architecture Diagrams

Phase-specific documentation continues through:

* Phase 5.0 — Shopping Cart
* Phase 5.1 — Checkout
* Phase 5.2 — Orders
* Phase 5.3 — Payments
* Phase 5.4 — Inventory Reservation
* Phase 5.5 — Shipment & Fulfillment
* Phase 5.6 — Returns & Refunds
* Phase 5.7 — Promotions & Discount Engine
* Phase 5.8 — Customer Notifications & Commerce Events
* Phase 5.9 — Commerce Event Reliability
* Phase 5.10 — Retailer Operations & Inventory Management
* Phase 5.11 — Retailer Catalog & Inventory Ingestion Foundation

Future phases must be added only after their business objective and technical scope have been established.

---

# Decision authority

The documents use:

* **MUST** — required for correctness, security, or an accepted architectural decision.
* **SHOULD** — default unless a documented trade-off justifies an exception.
* **MAY** — optional.

If documents conflict, apply this precedence:

1. Product boundary and business requirements.
2. Security and data-integrity requirements.
3. System architecture and API standards.
4. Coding and contribution conventions.
5. Roadmap and sprint sequencing.

An architectural decision that changes a MUST requirement requires an ADR and corresponding documentation updates.

---

# Shared definitions

| Term               | Meaning                                                                                |
| ------------------ | -------------------------------------------------------------------------------------- |
| Store              | A participating physical retailer in Manipur.                                          |
| Store owner        | Principal user responsible for a store account and staff access.                       |
| Store staff        | Authorized user operating permitted parts of a store account.                          |
| Product            | Merchandising information describing an item or style.                                 |
| Variant            | Specific selectable product combination, normally size/color.                          |
| Inventory item     | Store-specific stock for a product variant.                                            |
| Available quantity | Quantity eligible for new commerce activity after applicable holds.                    |
| Reservation        | Time-limited inventory hold associated with a customer/order workflow.                 |
| Search document    | Rebuildable denormalized representation in Meilisearch.                                |
| Inventory movement | Immutable record describing an inventory quantity change or reconciliation.            |
| Commerce event     | Durable event describing a committed business-domain transition.                       |
| System of record   | PostgreSQL state whose committed data is authoritative.                                |
| Data ingestion     | Process of converting external retailer information into the canonical platform model. |

---

# Initial retailer rollout strategy

The initial market is Manipur, beginning with clothing and apparel retailers.

The platform should minimize the work required from retailers to participate.

The preferred operational strategy is:

```text
Recruit retailer
      ↓
Collect existing data if available
      ↓
Otherwise platform staff collect data
      ↓
Prepare standardized spreadsheet
      ↓
Validate catalog + variants + prices + images + stock
      ↓
Import into platform
      ↓
Retailer verifies data
      ↓
Store becomes discoverable
      ↓
Retailer maintains operations
```

The platform should not require every retailer to become technically sophisticated before joining.

The objective is to make onboarding a **business operation**, not a software-integration project.

---

# Business model principle

Fashion Network is fundamentally a **retailer-network platform**.

Its value increases as more stores and more accurate inventory enter the network.

The platform therefore optimizes for:

* retailer participation;
* inventory coverage;
* catalog completeness;
* inventory accuracy;
* customer discovery;
* order conversion;
* retailer retention;
* operational efficiency.

Retailers are not merely suppliers of products to a marketplace.

They are participating businesses whose existing physical inventory becomes digitally discoverable through the network.

The platform should therefore avoid unnecessary requirements that force retailers to change how they already operate.

---

# Initial delivery assumptions

* Launch region: Manipur.
* Initial vertical: clothing and apparel.
* First production experience: responsive web platform.
* Retailers may be offline-first or already active on Instagram/Facebook.
* All retailers ultimately use the same canonical catalog and inventory model.
* Initial data acquisition uses structured spreadsheets and platform-assisted onboarding where necessary.
* Product images are part of catalog onboarding.
* Platform staff may perform initial catalog/data entry during the controlled rollout.
* Retailers remain responsible for the accuracy of their catalog and physical inventory.
* Search remains a rebuildable projection.
* PostgreSQL remains the transactional source of truth.
* Direct POS integrations are future capabilities, not prerequisites for launch.
* The platform should evolve toward progressively more automated inventory synchronization.

---

# Definition of readiness for future phases

A future phase should not be started merely because another backend module can be built.

Before beginning a new phase, the team MUST establish:

1. the business problem being solved;
2. the retailer/customer outcome;
3. the operational workflow;
4. the data ownership model;
5. whether the capability is required for launch;
6. how it affects retailer onboarding or retention;
7. how it affects catalog/inventory accuracy;
8. how it affects customer discovery or conversion;
9. the technical boundary;
10. the validation and operational requirements.

Technical implementation must follow the business objective rather than create unnecessary complexity.

---

# Current project position

The platform has completed its core commerce and retailer-ingestion foundation
through **Phase 5.11**.

The next development decision should therefore be driven by the actual marketplace objective:

> **Get real Manipur retailers and real products into the network, keep their catalog and inventory accurate, make those products discoverable, and create a repeatable retailer operating model.**

The next phase should be evaluated against that objective before additional infrastructure or domain complexity is introduced.
