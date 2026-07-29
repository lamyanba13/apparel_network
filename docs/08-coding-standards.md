# Coding Standards

## Goals

These standards keep the future implementation readable, secure, testable, and consistent with Clean Architecture, SOLID, and feature ownership. They govern application code when development begins; this documentation phase contains no application code.

## General principles

- Prefer explicit, simple code over clever abstraction.
- Keep business language consistent with the glossary.
- Make invalid states difficult to represent and impossible to persist where practical.
- Separate policy from transport, frameworks, and storage.
- Keep functions and classes focused on one reason to change.
- Depend on small interfaces owned by the consumer.
- Add abstraction after a real boundary or repeated stable concept is known, not in anticipation of hypothetical reuse.
- Errors are part of contracts and are handled deliberately.
- Comments explain why, constraints, or non-obvious trade-offs; code should explain what.
- No warnings, disabled checks, or TODOs enter main without an owner and tracked issue.

## SOLID application

### Single responsibility

Routers translate HTTP, application services coordinate a use case, domain objects enforce domain rules, repositories persist aggregates, and adapters talk to external systems. A class that validates permissions, executes SQL, sends notifications, and builds an HTTP response violates this rule.

### Open/closed

Use policies and adapter ports where supported variation is real, such as notification providers or storage. Do not create plugin systems for fixed domain rules.

### Liskov substitution

Test port implementations against shared contract tests. An in-memory repository used in unit tests must preserve relevant semantics such as uniqueness and not pretend to prove PostgreSQL locking behavior.

### Interface segregation

Define use-case-specific ports. A search indexer should not depend on a storage adapter's deletion API when it only reads verified media metadata.

### Dependency inversion

Application/domain layers own the abstractions needed from persistence, clocks, identifiers, queues, and providers. Bootstrap code supplies implementations.

## Python standards

- Use the currently approved supported Python version and pin it for local, CI, and production use.
- Require type annotations for public functions, services, repositories, and domain behavior.
- Use a strict static type checker configuration; exceptions are narrow and documented.
- Format and lint with one centrally configured toolchain.
- Prefer immutable value objects for identifiers, quantities, and state where practical.
- Use timezone-aware UTC datetimes.
- Use `Decimal` for any approved price representation.
- Never use mutable default arguments.
- Catch specific exceptions. Preserve causes when translating infrastructure errors.
- Do not use broad exception handling to return success or hide partial failure.
- Do not perform I/O at import time.
- Do not create implicit database sessions in domain code.

The initial Python toolchain is Ruff for formatting/linting, Pyright in strict mode for static typing, pytest for tests, and pre-commit for fast local checks. A change of tool requires one repository-wide configuration update, not feature-specific alternatives.

### FastAPI

- Routers remain thin and contain no persistence queries.
- Dependencies authenticate and construct request context; use cases authorize actions.
- Request and response models are separate from ORM models.
- Response schemas explicitly control public fields.
- Endpoint functions declare status codes and typed error outcomes in API documentation.
- Blocking I/O must not run on the asynchronous event loop.
- Middleware is limited to cross-cutting transport concerns such as request IDs, safe logging, and security headers.

### SQLAlchemy and PostgreSQL

- Use explicit transaction boundaries and dependency-scoped sessions.
- Repositories never commit independently when participating in a larger use case; the unit of work owns commit/rollback.
- Eliminate N+1 queries intentionally with explicit loading or read models.
- Every list query is bounded and paginated.
- Tenant-owned repository methods require a store identifier or tenant scope explicitly.
- Raw SQL is allowed when it materially improves correctness or performance, but it is parameterized, tested, and documented.
- Database constraints back critical invariants.
- Query plans are captured for new high-volume or latency-sensitive queries.
- Avoid ORM cascade behavior that can delete large graphs unexpectedly.

### Alembic

- Migration identifiers are unique and ordered from one head.
- Review generated types, defaults, indexes, foreign keys, and downgrade behavior.
- Separate schema expansion, data backfill, and schema contraction for risky changes.
- Large backfills run in bounded batches and are observable.
- Do not add a non-null column with an expensive table-wide default in one unsafe production step.
- Production schema changes occur only through the deployment process.

### Celery

- Task payloads contain identifiers and small versioned data, not ORM objects.
- Tasks are idempotent and assume at-least-once delivery.
- Define retryable versus terminal exceptions.
- Use bounded exponential backoff with jitter.
- Set soft/hard time limits appropriate to the queue.
- Acknowledge only according to the selected loss/duplicate trade-off.
- Never rely on task execution order unless encoded by durable state.
- Log task ID, event ID, attempt, correlation ID, and safe target identifiers.

## TypeScript and React standards

- Enable TypeScript strict mode and no unchecked implicit escape hatches.
- `any` requires a localized justification; prefer `unknown` with validation.
- Validate untrusted runtime data at the boundary even when compile-time types exist.
- Generate API types from the reviewed OpenAPI contract.
- Components receive narrow typed props.
- Keep data fetching in feature API layers or approved server boundaries, not scattered through presentation components.
- Avoid duplicating server business rules. Client checks improve usability but do not establish authority.
- Use semantic HTML before custom widgets.
- Every interactive control supports keyboard, focus, accessible name, and relevant status announcement.
- Effects are for synchronization with external systems, not derived state.
- State belongs at the lowest level that needs it; server state uses an approved consistent fetching/cache approach.
- Memoization is performance work backed by measurement, not a default style.
- Errors distinguish validation, authentication, authorization, conflict, rate limit, dependency outage, and unknown failure.

The initial TypeScript toolchain is pnpm workspaces, TypeScript strict checking, ESLint, Prettier, Vitest, React Testing Library, Playwright, and axe-based automated accessibility checks. ESLint owns correctness rules and Prettier owns formatting; overlapping format rules are disabled.

### Next.js

- Routes define composition, metadata, loading, and error boundaries.
- Cache behavior is explicit for every server-side fetch.
- Authenticated or store-specific content is private/no-store unless a reviewed cache key safely scopes it.
- Revalidation cannot be the only mechanism protecting reservation or inventory correctness.
- Server actions or route handlers, if used, call the backend API or a documented adapter; they do not become a second domain implementation.
- Browser bundles contain no server secrets.

### TailwindCSS and UI

- Use shared tokens for color, typography, spacing, radius, and elevation.
- Extract repeated semantic patterns into accessible primitives.
- Avoid arbitrary values when a token should exist.
- Responsive designs begin with constrained mobile layouts and are tested at content extremes.
- Availability and validation states use text/iconography in addition to color.

## Naming

Use business terms exactly:

- `on_hand_quantity`: physical quantity recorded by the store;
- `held_quantity`: quantity in active durable holds;
- `available_quantity`: derived reservable quantity;
- `reservation`: a time-limited hold workflow, never an order;
- `store_membership`: scoped relationship, never a global role alone.

Avoid vague names such as `data`, `manager`, `processor`, or `handle` when a business action can be named. Boolean names read as predicates (`is_active`, `can_publish`). Collection names are plural.

## Errors

Domain errors describe business outcomes such as insufficient availability or invalid reservation transition. Application services translate infrastructure problems into stable application failures. Presentation maps these to the standard API error envelope.

- Never expose stack traces, SQL, object keys, provider messages, or secrets to clients.
- Do not use exceptions for expected collection emptiness.
- Conflicts caused by current resource state use consistent machine-readable codes.
- Retry advice is returned only when retry is safe.
- Logs record one authoritative error event at the correct boundary to avoid duplicate noise.

## Contract-first workflow

For an HTTP change:

1. update the reviewed OpenAPI contract and examples;
2. run schema lint and breaking-change analysis;
3. obtain API and affected-client review;
4. generate the TypeScript client/types;
5. implement FastAPI behavior against the contract;
6. compare FastAPI's generated implementation view to the reviewed contract in CI;
7. run contract, authorization, and consumer tests.

Implementation-specific schemas may be generated from or mapped to the contract, but they cannot silently redefine it. Integration events follow the same design-review/version/conformance approach with versioned schemas.

## Logging and telemetry

- Log structured events, not concatenated prose.
- Use stable event names and safe opaque IDs.
- Never log passwords, authentication headers, session/refresh tokens, signed URLs, full upload metadata, or unnecessary personal data.
- Do not log full request/response bodies by default.
- Correlation IDs propagate into SQL-adjacent diagnostics, outbox events, Celery tasks, Sentry, and provider calls where supported.
- Analytics event names and properties require tracking-plan review.

## Testing strategy

### Unit tests

Test pure domain rules, policies, state machines, permission decisions, mapping, and application orchestration with controlled ports. Unit tests are deterministic and make no network calls.

### Integration tests

Use real PostgreSQL behavior for constraints, transactions, locking, repository queries, migrations, and outbox delivery. Use real Redis/Meilisearch containers for adapter behavior that mocks cannot prove.

### Contract tests

Validate:

- OpenAPI compatibility and generated client expectations;
- module facade contracts;
- event schema compatibility;
- provider adapters against recorded/sandbox contracts without embedding secrets.

### End-to-end tests

Cover a small set of critical paths:

- store approval and publication;
- inventory update through public discovery;
- successful reservation;
- concurrent reservation with insufficient remaining stock;
- cancellation/expiry and released availability;
- store suspension removing discovery;
- cross-store access denial;
- privileged admin action and audit evidence.

### Performance and resilience tests

Exercise search load, high-contention reservation rows, large inventory lists/imports, index rebuild, queue backlog, Redis loss, and provider failure. Tests must assert correctness in addition to latency.

The baseline suite also exercises RabbitMQ interruption/redelivery, outbox recovery, R2-versus-MinIO contract differences, OpenAPI drift, optimistic version conflicts, audit append-only permissions, and search reconciliation at representative data volumes.

## Test quality rules

- Tests describe observable behavior, not implementation trivia.
- A bug fix starts with a failing regression test when feasible.
- Time, identifiers, and external effects are controllable.
- Flaky tests are fixed or quarantined with an owner and deadline; they are not silently retried forever.
- Snapshot tests are limited to stable presentation/contract outputs and reviewed meaningfully.
- Coverage thresholds may prevent sharp regressions, but critical business rules require explicit scenario coverage.

## Local quality gates

Pre-commit runs only fast deterministic checks: whitespace/encoding, secret detection, Ruff, targeted ESLint/Prettier, and contract syntax. Type checking and focused unit tests SHOULD run before push. Integration, container, full E2E, migration, compatibility, performance, and security suites run in CI because they require controlled services or more time.

Conventional Commits are enforced with commitlint for commits and merge/squash titles. Repository branching, rebasing, tagging, and releases follow the controlled `main`/`develop` strategy in [Git Workflow](git-workflow.md). Working, release, and hotfix branches remain short-lived. Release versions use Semantic Versioning for external contracts and independently recorded deploy release identifiers for applications.

## Review checklist

Every implementation review asks:

- Does the change preserve product scope?
- Is the behavior owned by the correct module?
- Are authorization and tenant scope explicit?
- Are business invariants protected transactionally and by constraints?
- Are retries and concurrent execution safe?
- Does the API remain compatible and minimize data?
- Are search/cache/notification side effects after commit and replayable?
- Are logs, errors, analytics, and uploads privacy-safe?
- Are migrations and rollback/roll-forward safe?
- Do tests prove the failure paths as well as success?
- Are documentation and runbooks updated?
