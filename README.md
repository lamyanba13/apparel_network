# Fashion Network

Fashion Network is the digital inventory infrastructure for participating clothing stores in Manipur. Customers discover products across stores, while stores retain ownership of inventory and fulfill their own reservations. It is not an e-commerce platform.

Phase 1.1 contains only the production project foundation. It includes no authentication, business modules, database models, migrations, catalog behavior, inventory behavior, reservations, or commerce functionality.

## Architecture

The repository is a modular monolith with three deployable applications:

- `frontend/`: public Next.js App Router application.
- `dashboard/`: store and administrator Next.js App Router application.
- `backend/`: Python 3.13 FastAPI application and future Celery workers.

Feature boundaries are reserved under `backend/app/modules/`. PostgreSQL will be authoritative when persistence is implemented; Redis, RabbitMQ, Meilisearch, Cloudflare R2, and other integrations are not wired during Phase 1.1.

The complete architecture and product requirements are in [`docs/`](docs/README.md). Documentation is the source of truth.

## Prerequisites

- Python 3.13
- Poetry
- Node.js 24 or another version supported by the pinned Next.js release
- Corepack and pnpm
- GNU Make is optional; every Make target maps to a documented native command

## Install

From the repository root:

```text
poetry --directory backend install
corepack enable
corepack pnpm install
```

Copy `.env.example` to `.env` for local overrides. Phase 1.1 does not require any external service to start the applications.

## Start development

Backend:

```text
poetry --directory backend run uvicorn app.main:app --reload
```

Public frontend:

```text
corepack pnpm dev:frontend
```

Dashboard:

```text
corepack pnpm dev:dashboard
```

The only backend endpoint is `GET /health`.

## Quality checks

```text
make lint
make typecheck
make test
make build
```

Equivalent pnpm and Poetry commands are defined in the root `package.json`, backend `pyproject.toml`, and GitHub Actions workflows.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before making changes. The authoritative branch, commit, rebase, merge, tag, release, and Git-alias guidance is in [`docs/git-workflow.md`](docs/git-workflow.md). Security vulnerabilities must be reported privately as described in [`SECURITY.md`](SECURITY.md).

## Repository structure

```text
.
├── frontend/         Public customer web foundation
├── dashboard/        Store and admin web foundation
├── backend/          FastAPI modular-monolith foundation
├── infrastructure/   Environment, proxy, container, monitoring, and IaC placeholders
├── docs/             Approved product and architecture documentation
├── scripts/          Future safe developer and operational entry points
└── .github/          Continuous-integration workflows
```

Infrastructure placeholders intentionally contain no Docker images, Nginx configuration, cloud resources, or production credentials yet.
