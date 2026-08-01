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
