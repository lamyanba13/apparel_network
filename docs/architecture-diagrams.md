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
    hours --> status

    profile --> postgres
    verification --> postgres
    membership --> postgres
    media --> postgres
    media --> objects
    hours --> postgres

    store -. principal and permission contracts .-> identity
    store --> telemetry
    future -. application contracts only .-> status
```

Operating hours do not represent inventory availability, reservation
capacity, delivery windows, or employee shifts. PostgreSQL remains
authoritative; the status resolver requires no Redis, RabbitMQ, search, or
background-job dependency.
