# Foundation Architecture Diagrams

These diagrams describe the frozen foundation at `foundation-v1`. They show architectural boundaries, not implemented business workflows. PostgreSQL is authoritative; Redis, Meilisearch, RabbitMQ, and object storage never replace transactional ownership.

## System architecture

```mermaid
flowchart LR
    customer[Customer browser]
    operator[Store or admin browser]
    edge[Edge / reverse proxy]
    frontend[Customer Next.js app]
    dashboard[Dashboard Next.js app]
    api[FastAPI modular monolith]
    worker[Celery worker]

    postgres[(PostgreSQL)]
    redis[(Redis)]
    rabbit[(RabbitMQ)]
    search[(Meilisearch)]
    objects[(R2 / local MinIO)]

    customer --> edge --> frontend
    operator --> edge --> dashboard
    frontend --> api
    dashboard --> api
    api --> postgres
    api --> redis
    api --> search
    api --> objects
    api --> rabbit
    rabbit --> worker
    worker --> postgres
    worker --> redis
    worker --> search
    worker --> objects
```

RabbitMQ is the Celery broker. Redis is restricted to caching, sessions, rate limiting, temporary reservation locks, and ephemeral coordination.

## Backend module diagram

```mermaid
flowchart TB
    delivery[HTTP delivery and middleware]
    shared[Core contracts and infrastructure adapters]

    subgraph identity[Identity and access delivery phase]
        auth[Auth]
        users[Users]
    end

    stores[Stores]
    products[Products]
    inventory[Inventory]
    reservations[Reservations]
    search[Search]
    notifications[Notifications]
    admin[Admin]
    analytics[Analytics]
    uploads[Uploads]

    delivery --> auth
    delivery --> users
    delivery --> stores
    delivery --> products
    delivery --> inventory
    delivery --> reservations
    delivery --> search
    delivery --> admin

    auth --> shared
    users --> shared
    stores --> shared
    products --> shared
    inventory --> shared
    reservations --> shared
    search --> shared
    notifications --> shared
    admin --> shared
    analytics --> shared
    uploads --> shared
```

The grouping of Auth and Users represents roadmap sequencing only. Both remain explicit approved module boundaries. Modules collaborate through application services and contracts, not another module's repository internals.

## Foundation health sequence

```mermaid
sequenceDiagram
    participant Client
    participant Proxy as Nginx / ingress
    participant API as FastAPI
    participant Middleware
    participant Checks as Readiness checks
    participant Dependencies as PostgreSQL / Redis / RabbitMQ / Meilisearch / object storage

    Client->>Proxy: GET /health/ready
    Proxy->>API: Forward request + correlation context
    API->>Middleware: Apply request policies
    Middleware->>Checks: Invoke readiness handler
    Checks->>Dependencies: Bounded dependency probes
    Dependencies-->>Checks: Per-dependency status
    Checks-->>Middleware: Aggregate readiness response
    Middleware-->>API: Headers, metrics, structured log
    API-->>Proxy: HTTP response
    Proxy-->>Client: HTTP response
```

## Empty ER foundation

No business database models or migrations exist at the architecture-freeze boundary. The correct foundation ER diagram is intentionally empty:

```mermaid
erDiagram
    %% Intentionally empty at foundation-v1.
    %% Domain entities begin with approved product phases.
```

Future entity design must establish module ownership, identifiers, constraints, lifecycle rules, and migration strategy before entities are added here. This diagram must not be treated as permission to infer a business schema.

## Request flow

```mermaid
flowchart LR
    request[HTTP request]
    proxy[Reverse proxy]
    correlation[Correlation and security middleware]
    limits[Rate limit and request policies]
    route[Versioned route adapter]
    service[Application service]
    port[Repository or provider port]
    adapter[Infrastructure adapter]
    dependency[(External dependency)]
    response[Contract response]
    telemetry[Logs, metrics, traces, errors]

    request --> proxy --> correlation --> limits --> route --> service --> port --> adapter --> dependency
    dependency --> adapter --> port --> service --> route --> response
    correlation -.-> telemetry
    limits -.-> telemetry
    route -.-> telemetry
    service -.-> telemetry
    adapter -.-> telemetry
```

Feature routes and services are future work. The flow fixes dependency direction: HTTP and provider details remain outside domain behavior.

## Completed Identity module

The Phase 2.6 Identity implementation remains one feature module inside the
modular monolith. The branches below are capabilities, not separately deployed
services.

```mermaid
flowchart TB
    identity[Identity]

    persistence[Persistence]
    authentication[Authentication]
    sessions[Sessions]
    authorization[Authorization]
    accountSecurity[Account Security]
    cleanup[Cleanup]
    events[Events]
    metrics[Metrics]
    notifications[Notifications]
    publicApi[Public API]

    postgres[(PostgreSQL)]
    redis[(Redis)]
    shared[Shared platform contracts]
    futureModules[Future business modules]

    identity --> persistence
    identity --> authentication
    identity --> sessions
    identity --> authorization
    identity --> accountSecurity
    identity --> cleanup
    identity --> events
    identity --> metrics
    identity --> notifications
    identity --> publicApi

    persistence --> postgres
    authentication --> persistence
    sessions --> persistence
    authorization --> redis
    authorization --> persistence
    accountSecurity --> persistence
    cleanup --> persistence
    events --> shared
    metrics --> shared
    notifications --> shared
    publicApi --> authentication
    publicApi --> sessions
    publicApi --> accountSecurity
    futureModules --> authorization
    futureModules -. principal and policy contracts .-> identity
```

Identity does not import Store, Catalog, Inventory, Reservation, or Marketplace
packages. Its known Phase 2.4 business-vocabulary qualification and supported
interface allowlist are documented in the
[Identity Enterprise Review](identity-enterprise-review.md).

## Completed Store capabilities through Phase 3.5

The Store feature remains one bounded context and one deployable part of the
modular monolith. Its subdomains share the Store ownership boundary but expose
separate application contracts.

```mermaid
flowchart TB
    store[Store bounded context]
    profile[Profile and lifecycle]
    verification[Verification]
    membership[Membership]
    media[Media]
    hours[Operating hours]
    status[Business status resolver]
    storeAnalytics[Operational analytics]

    identity[Identity public contracts]
    postgres[(PostgreSQL)]
    objects[(R2 / local MinIO)]
    telemetry[Safe events and metrics]
    future[Future approved consumers]

    store --> profile
    store --> verification
    store --> membership
    store --> media
    store --> hours
    store --> storeAnalytics
    hours --> status

    profile --> postgres
    verification --> postgres
    membership --> postgres
    media --> postgres
    media --> objects
    hours --> postgres
    storeAnalytics --> postgres

    store -. principal and permission contracts .-> identity
    store --> telemetry
    future -. application contracts only .-> status
```

Operating hours do not represent inventory availability, reservation
capacity, delivery windows, or employee shifts. PostgreSQL remains
authoritative; the status resolver requires no Redis, RabbitMQ, search, or
background-job dependency.

Store operational analytics is a transactional PostgreSQL projection over
safe Store events. It is not a separate service, warehouse, PostHog dataset,
or business-intelligence boundary. Redis and RabbitMQ are not involved.

## Phase 3.7 Store search and discovery

```mermaid
flowchart LR
    postgres[(PostgreSQL authoritative Store data)]
    events[Store domain events]
    rabbit[RabbitMQ]
    worker[Celery store-search worker]
    projection[Public Store projection]
    meili[(Meilisearch stores index)]
    api[Public search API]
    admin[System rebuild API]

    postgres --> events --> rabbit --> worker
    worker --> projection --> meili
    api --> meili
    admin --> rabbit
```

Search is a rebuildable, asynchronous projection. HTTP requests never write
Meilisearch directly. Only verified, active, public, non-deleted stores are
projected; owner, contact, membership, audit, and verification-note data is
never indexed. RabbitMQ is the Celery broker and Redis remains unrelated to
search durability.

## Phase 4.0 Catalog foundation

```mermaid
flowchart LR
    identity[Identity permissions]
    store[Owned Store]
    api[Catalog API]
    service[Catalog application services]
    postgres[(PostgreSQL catalogs)]
    events[Safe Catalog events]

    identity --> api
    store --> api
    api --> service --> postgres
    service --> events
```

Catalog is Store-owned metadata. It has no dependency on Products, Inventory,
Pricing, Reservations, or search. PostgreSQL remains the system of record and
catalog repositories never commit transactions.

## Phase 4.1 Product foundation

```mermaid
flowchart LR
    store[Owned Store]
    catalog[Catalog]
    api[Product API]
    product[Product services]
    postgres[(PostgreSQL products)]
    events[Safe Product events]

    store --> catalog
    catalog --> api
    api --> product --> postgres
    product --> events
```

Products are Catalog-owned and Store-scoped. Product persistence does not
introduce inventory, pricing, variants, media, reservations, or new
infrastructure.

## Phase 4.3 Product Media

```mermaid
flowchart LR
    product[Product] --> api[Product Media API]
    api --> service[Media service]
    service --> postgres[(PostgreSQL metadata)]
    service --> storage[StorageProvider / MinIO]
    service --> events[Safe media events]
```

Product Media is metadata-owned by Products while binary objects remain in the
existing storage abstraction. Database transactions and compensating object
operations are coordinated by the HTTP dependency; Redis and RabbitMQ are not
used for media persistence.

## Phase 4.5 Inventory Foundation

```mermaid
flowchart LR
    api[Inventory API] --> service[Inventory application service]
    service --> repository[Inventory repository]
    repository --> postgres[(PostgreSQL inventory_items)]
    service --> events[Safe inventory events]
    variant[Product Variant] --> repository
```

Inventory is a separate bounded context. It owns one authoritative stock record
per active Product Variant and does not own reservations, movement history,
search projections, pricing, or multi-location operations.

## Phase 4.6 Product Pricing Foundation

```mermaid
flowchart LR
    identity[Pricing permissions] --> api[Product Pricing API]
    store[Owned Store] --> policy[Pricing ownership policy]
    catalog[Catalog] --> policy
    product[Product] --> policy
    variant[Optional Product Variant] --> policy
    api --> service[Pricing application service]
    service --> policy
    service --> repository[Pricing repository]
    repository --> postgres[(PostgreSQL product_prices)]
    service --> events[Identifier-only Pricing events]
    service --> metrics[Low-cardinality Pricing metrics]
```

Pricing is independent from Product description and Inventory quantity. Its
application policy validates the complete Store/Catalog/Product/Variant ownership
chain, while PostgreSQL owns price constraints, effective periods, audit state,
soft deletion, and optimistic version persistence.

## Phase 4.8 Variant Attribute Normalization

```mermaid
flowchart LR
    identity[Attribute permissions] --> api[Attribute and Variant APIs]
    store[Owned Store] --> service[Attribute services]
    api --> service
    service --> definitions[Product attributes and values]
    service --> assignments[Normalized Variant assignments]
    assignments --> signature[Deterministic combination signature]
    service --> outbox[Transactional event outbox]
    definitions --> postgres[(PostgreSQL)]
    assignments --> postgres
    outbox --> postgres
```

The Product Variant API remains compatible, but free-form input must resolve to
controlled values. Variant mutations and identifier-only outbox events flush in
one request transaction; dispatch and downstream projection are deferred.

## Phase 4.7 Price Lists & Multi-Currency

```mermaid
flowchart LR
    identity[Price List and resolution permissions] --> api[Price List API]
    api --> lists[Price List service]
    api --> resolver[Pricing resolver]
    store[Owned Store] --> lists
    product[Product and optional Variant] --> resolver
    lists --> listrepo[Price List repositories]
    listrepo --> postgres[(PostgreSQL)]
    resolver --> order[Specificity, group, priority, schedule, UUID]
    order --> postgres
    lists --> events[Identifier-only events]
    resolver --> events
    lists --> metrics[Low-cardinality metrics]
    resolver --> metrics
```

Price Lists reference authoritative Product Prices through assignments. The
resolver never converts currency: it selects only explicit records matching the
requested ISO-4217 code and timestamp. Unassigned Product Prices provide the
backward-compatible default-Store fallback.

## Phase 5.0 Shopping Cart Foundation

```mermaid
flowchart LR
    identity[Authenticated customer and Cart permissions] --> api[Cart API]
    api --> service[Cart application service]
    service --> ownership[Customer ownership policy]
    service --> pricing[Production PricingResolver]
    service --> inventory[Production InventoryService]
    pricing --> snapshot[Persisted price snapshot]
    inventory --> validation[Availability validation only]
    service --> repositories[Cart repository ports]
    repositories --> postgres[(PostgreSQL Carts and Items)]
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
```

Cart reads and summaries use persisted snapshots. Pricing and Inventory are called
only when an Item is added or its quantity changes. Inventory is not reserved, and
checkout, Orders, tax, shipping, payments, conversion, and coupons remain outside
the Phase 5.0 boundary.

## Phase 5.1 Checkout Foundation

```mermaid
flowchart LR
    customer[Authenticated customer] --> api[Checkout API]
    api --> service[Checkout application service]
    service --> cart[Production Cart service]
    service --> pricing[Production PricingResolver]
    service --> inventory[Production InventoryService]
    pricing --> snapshots[Immutable Checkout Item snapshots]
    inventory --> snapshots
    service --> sessions[Checkout repositories]
    sessions --> postgres[(PostgreSQL)]
    snapshots --> postgres
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
    service -. confirmed immutable data .-> order[Future Order boundary]
```

Checkout creation revalidates rather than copying Cart snapshots. Confirmation
transitions the Cart and Checkout atomically but does not reserve Inventory, create
an Order, process Payment, or calculate tax or shipping.

## Phase 5.2 Order Foundation

```mermaid
flowchart LR
    customer[Authenticated customer] --> api[Order API]
    api --> service[Order application service]
    service --> checkout[Production Checkout service]
    checkout --> snapshots[Confirmed immutable snapshots]
    snapshots --> repositories[Order repository ports]
    service --> numbering[PostgreSQL Order number sequence]
    repositories --> postgres[(PostgreSQL Orders and Items)]
    numbering --> postgres
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
    service -. confirmed contract .-> payment[Future Payment boundary]
```

Order creation copies confirmed Checkout snapshots and never reads mutable Cart
Items. Orders do not mutate Inventory or implement Payment, tax, shipping,
invoicing, or fulfillment.

## Phase 5.3 Payment Foundation

```mermaid
flowchart LR
    customer[Authenticated customer] --> api[Payment API]
    api --> service[Payment application service]
    service --> order[Production Order service]
    service --> gateway[PaymentGateway protocol]
    gateway --> null[Deterministic Null gateway]
    service --> intents[Payment repositories]
    intents --> postgres[(PostgreSQL Intents and Transactions)]
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
    service -. successful capture .-> order
    gateway -. future adapters .-> providers[Razorpay / Stripe / Cashfree]
```

Payment snapshots a pending Order and never reads Checkout or writes Order tables.
The Null gateway performs no financial transaction. A captured Payment asks the
Order service to confirm the Order in the shared request transaction.

## Phase 5.4 Inventory Reservation

```mermaid
flowchart LR
    customer[Authenticated customer] --> api[Reservation API]
    api --> service[Reservation application service]
    service --> payment[Production Payment service]
    service --> order[Production Order service]
    service --> checkout[Production Checkout service]
    service --> inventory[Production Inventory service]
    inventory --> lock[Stable row locks and validation]
    service --> holds[Active Reservation capacity]
    holds --> repositories[Reservation repositories]
    repositories --> postgres[(PostgreSQL Reservations and Items)]
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
    service -. consumed Reservation .-> fulfillment[Future Fulfillment]
```

Active Reservations subtract from reservable capacity without changing Inventory
columns. Lazy expiration, release, and consumption terminate the hold; future
Fulfillment remains responsible for approved Inventory adjustment.

## Phase 5.5 Shipment & Fulfillment Foundation

```mermaid
flowchart LR
    customer[Authenticated customer] --> api[Shipment API]
    api --> service[Shipment application service]
    service --> payment[Production Payment service]
    service --> order[Production Order service]
    service --> reservation[Production Reservation service]
    service --> gateway[ShippingGateway protocol]
    gateway --> null[Deterministic Null carrier]
    service --> repositories[Shipment repositories]
    repositories --> postgres[(PostgreSQL Shipments Packages Tracking)]
    service --> inventory[Production Inventory service]
    inventory --> stock[Locked Inventory consumption]
    stock --> postgres
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
```

Shipment creation validates the captured commercial chain and consumed
Reservation. Dispatch changes stock only through InventoryService; Shipment owns
packages, tracking, fulfillment lifecycle, and carrier abstraction without writing
Payment, Order, Reservation, or Inventory persistence directly.

## Phase 5.6 Returns & Refund Foundation

```mermaid
flowchart LR
    customer[Purchasing customer] --> api[Return and Refund API]
    api --> service[Return application services]
    service --> order[Production Order service]
    service --> shipment[Production Shipment service]
    service --> payment[Production Payment service]
    service --> inventory[Production Inventory service validation]
    service --> repositories[Return and Refund repositories]
    repositories --> postgres[(PostgreSQL Returns Items Refunds Transactions)]
    service --> gateway[RefundGateway protocol]
    gateway --> null[Deterministic Null refund provider]
    service --> outbox[Identifier-only transactional outbox]
    outbox --> postgres
    inventory -. disposition only; no stock mutation .-> repositories
```

Returns validate immutable delivered purchase records and cumulative quantities.
Inspection persists disposition without restocking. Refunds derive immutable
commercial values and use a provider-neutral gateway without writing Payment data.
