# Folder Structure

## Monorepo layout

The implementation repository uses the following top-level structure. Phase
1.5 includes the project skeleton, local container infrastructure, asynchronous
database foundation, business-neutral shared application framework, and
reliability/observability operations foundation; later feature artifacts remain
intentional future structure.

```text
/
├── frontend/                 # Public customer Next.js application
├── dashboard/                # Store and administrator Next.js application
├── backend/                  # FastAPI modular monolith and Celery processes
├── packages/                 # Narrow frontend workspace packages
├── infrastructure/           # Deployment and local infrastructure definitions
├── docs/                     # Product, architecture, operations, and ADRs
├── scripts/                  # Thin, documented developer/operations entry points
├── .github/                  # GitHub Actions workflows and repository templates
├── .editorconfig
├── .gitignore
├── .env.example             # Documented local configuration template
├── .env.development         # Development-only Compose defaults
├── package.json              # pnpm workspace scripts only
├── pnpm-workspace.yaml
├── docker-compose.yml       # Complete local development orchestration
└── README.md                # Repository entry point linking to docs/
```

Generated files, dependencies, build outputs, local secrets, uploaded media, and production data MUST NOT be committed.

## Public frontend

```text
frontend/
├── src/
│   ├── app/                  # Next.js routes, layouts, loading/error boundaries
│   ├── features/
│   │   ├── auth/
│   │   ├── discovery/
│   │   ├── products/
│   │   ├── stores/
│   │   ├── reservations/
│   │   └── account/
│   ├── components/           # Application-wide composed UI, kept small
│   ├── design-system/        # Tokens and reusable presentation primitives
│   ├── lib/                  # Framework adapters: API client, analytics, config
│   ├── generated/            # Generated API types/client; never hand-edited
│   ├── styles/
│   └── test/
├── public/
├── e2e/
├── package.json
├── tsconfig.json
└── next.config.*
```

### Feature layout

Each feature may contain only the folders it needs:

```text
features/reservations/
├── api/                      # Feature API calls and transport mapping
├── components/               # Feature-specific UI
├── hooks/                    # Feature-specific client coordination
├── model/                    # View models and pure feature rules
├── schemas/                  # Client input schemas where needed
├── tests/
└── index.ts                  # Narrow public exports
```

Routes compose features. They do not become the location for reusable business or API logic. Features import shared design-system and lib adapters through public exports; they SHOULD NOT deep-import another feature's internals.

## Dashboard

```text
dashboard/
├── src/
│   ├── app/
│   │   ├── (store)/          # Store-scoped route group
│   │   └── (admin)/          # Administrator route group
│   ├── features/
│   │   ├── auth/
│   │   ├── store-profile/
│   │   ├── staff/
│   │   ├── catalog/
│   │   ├── inventory/
│   │   ├── reservations/
│   │   ├── uploads/
│   │   ├── store-analytics/
│   │   └── administration/
│   ├── components/
│   ├── design-system/
│   ├── lib/
│   ├── generated/
│   └── test/
├── public/
├── e2e/
└── package.json
```

Store selection is explicit in routes and API calls. A selected store in client state is never sufficient authorization. Administrative UI and store UI may share primitives, but admin-only components and routes must remain clearly separated.

## Shared frontend packages

The two Next.js applications use a pnpm workspace with deliberately narrow packages:

```text
packages/
├── api-client/               # Generated from reviewed OpenAPI; never hand-edited
├── ui/                       # Accessible primitives and shared design tokens
├── eslint-config/            # Shared lint rules
└── typescript-config/        # Shared strict compiler baselines
```

Do not create a package containing product feature logic from both applications. Do not add a monorepo task orchestrator until CI duration or dependency-graph evidence justifies it; pnpm workspaces and path-scoped GitHub Actions are sufficient initially.

## Backend

```text
backend/
├── src/
│   └── fashion_network/
│       ├── bootstrap/        # App factory, dependency wiring, process startup
│       ├── config/           # Typed environment configuration
│       ├── shared/
│       │   ├── domain/
│       │   ├── application/
│       │   ├── infrastructure/
│       │   └── presentation/
│       ├── modules/
│       │   ├── auth/
│       │   ├── users/
│       │   ├── stores/
│       │   ├── products/
│       │   ├── inventory/
│       │   ├── reservations/
│       │   ├── search/
│       │   ├── notifications/
│       │   ├── admin/
│       │   ├── audit/
│       │   ├── analytics/
│       │   └── uploads/
│       ├── api.py            # Composes module routers only
│       ├── worker.py         # Celery application composition
│       └── scheduler.py      # Scheduled task composition if separate
├── migrations/
│   ├── versions/
│   └── env.py
├── tests/
│   ├── architecture/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   ├── performance/
│   └── fixtures/
├── pyproject.toml
├── alembic.ini
└── Dockerfile
```

### Backend module template

```text
modules/inventory/
├── domain/
│   ├── entities/
│   ├── value_objects/
│   ├── services/
│   ├── events/
│   ├── errors.py
│   └── policies.py
├── application/
│   ├── commands/
│   ├── queries/
│   ├── dto/
│   ├── ports/
│   ├── repositories/
│   └── services/
├── infrastructure/
│   ├── persistence/
│   │   ├── models.py
│   │   ├── mappings.py
│   │   └── repositories.py
│   ├── tasks/
│   └── adapters/
├── presentation/
│   ├── api/
│   │   ├── router.py
│   │   ├── requests.py
│   │   └── responses.py
│   └── dependencies.py
├── facade.py                 # Narrow module-facing application interface
└── __init__.py               # No side effects
```

Folders should be created only when populated. The dependency rule is more important than symmetrical directory trees.

### Tests close to ownership

Pure domain and application unit tests MAY live alongside module code in `tests/` subfolders if the team standard chooses co-location. Cross-module, database, contract, and end-to-end tests remain in `backend/tests/`. Choose one consistent convention in the first backend PR.

## Infrastructure

```text
infrastructure/
├── tofu/
│   ├── modules/              # Reusable OpenTofu modules
│   └── environments/         # Environment composition; no secret values
├── docker/                   # Container support files if not app-local
├── monitoring/
│   ├── dashboards/
│   ├── alerts/
│   └── synthetic-checks/
├── runbooks/
│   ├── deployment.md
│   ├── rollback.md
│   ├── database-restore.md
│   ├── search-rebuild.md
│   ├── queue-backlog.md
│   └── incident-response.md
└── README.md
```

OpenTofu is the infrastructure-as-code standard. Environment composition lives under `infrastructure/tofu/environments/`; provider-agnostic reusable definitions live under `infrastructure/tofu/modules/`. Platform runtime manifests, if required, receive a clearly named sibling directory rather than duplicating environment ownership. Remote state is encrypted, locked, access-controlled, and separated by environment. Secret values never reside in this tree.

## Documentation

```text
docs/
├── README.md
├── 01-vision.md
├── ...
├── 16-contributing-guide.md
├── adr/
│   ├── README.md
│   └── NNNN-short-title.md
├── api/
│   ├── openapi.yaml          # Reviewed design-first API source of truth
│   ├── changelog.md
│   └── examples/
├── events/
│   ├── catalog.md            # Event ownership/version registry
│   └── schemas/              # Versioned JSON Schema or chosen schema format
├── data/
│   ├── dictionary.md
│   └── retention.md
├── product/
│   ├── taxonomy.md
│   └── analytics-tracking-plan.md
└── operations/
    ├── service-catalog.md
    └── incident-severity.md
```

The additional folders are created as their artifacts become real. `docs/api/openapi.yaml` is reviewed before endpoint implementation. FastAPI's generated implementation view is a CI artifact used for conformance comparison, not the design authority.

## Scripts

```text
scripts/
├── README.md
├── bootstrap.*
├── check.*
├── test.*
├── generate-api-client.*
├── validate-openapi.*
├── create-migration.*
└── verify-migration.*
```

Scripts are thin, noninteractive where possible, safe to rerun, and delegate to normal project tools. Each script documents prerequisites, inputs, side effects, exit codes, and examples. A script must not conceal destructive production operations behind a harmless name.

Business-neutral manual load examples live at `tests/load/` with k6, Locust,
and execution/reporting guidance. They are not run automatically in CI.

## Local Compose layout

The single `docker-compose.yml` starts the complete daily development runtime by default: PostgreSQL, Redis, RabbitMQ, Meilisearch, MinIO, Mailpit, backend, Celery worker, Flower, both Next.js applications, and a development-only Nginx gateway. The `tools` profile contains the one-shot environment verifier. Optional profiles are:

- `observability`: implemented OpenTelemetry Collector, Prometheus, and Grafana
  for local telemetry work;
- `resilience`: Toxiproxy or equivalent dependency-failure test support.

Containers use named volumes and health checks. Default ports bind only to loopback. Local credentials are fixed development-only values and cannot be accepted by non-local configuration validation.

## Naming and boundary rules

- Use lowercase kebab-case for Markdown filenames, except conventional uppercase repository files.
- Python modules and packages use `snake_case`; Python types use `PascalCase`.
- TypeScript source files use the project-agreed consistent convention; React components use `PascalCase`.
- Database tables and columns use `snake_case`.
- API paths use lowercase plural nouns and kebab-case for multiword segments.
- Environment variables use an application prefix and `UPPER_SNAKE_CASE`.
- Tests mirror the behavior or unit being tested; names describe outcomes.
- No directory named `utils` or `helpers` may become an unowned catch-all. Place code with the feature or name the shared capability precisely.
- Imports use public module entry points. Deep cross-feature imports and cross-module ORM imports are prohibited.

## Ownership

`CODEOWNERS` should map:

- each frontend application to its responsible team;
- backend module paths to feature owners;
- infrastructure and workflows to platform owners;
- security-sensitive Auth/Admin code to required reviewers;
- migrations to backend/data reviewers;
- documentation to the matching product or technical owner.

Ownership does not permit bypassing module review when a change crosses boundaries.
