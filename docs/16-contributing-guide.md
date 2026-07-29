# Contributing Guide

## Purpose

This guide defines how engineers, product contributors, designers, and operators safely change Fashion Network. Until implementation begins, contributions are documentation and architecture changes only.

## Product boundary

Every contribution must preserve the platform as an inventory network. Do not add checkout, payment processing, shipping, delivery, platform-owned inventory, commissions, settlement, returns, or platform fulfillment without an approved business-scope change.

Use the North-star decision test in [Vision](01-vision.md). If scope is unclear, raise a product decision before designing or implementing the feature.

## Before starting

1. Read the documentation map in [README](README.md).
2. Identify the relevant business and functional requirement IDs.
3. Check existing issues, ADRs, API changelog, data dictionary, and module owner.
4. Confirm the work meets Definition of Ready in the sprint plan.
5. For high-risk work, update or create the threat model before implementation.
6. Agree on cross-module contracts before parallel implementation begins.

Do not begin with a database table or endpoint and infer the user capability afterward.

Run the repository bootstrap and pre-commit setup before the first change. Ordinary local work uses the core Compose profile and requires no cloud credentials.

## Types of change

### Small change

A contained fix or documentation clarification with no contract, schema, security boundary, dependency, or architectural impact.

### Feature change

Implements approved functional requirements. It requires acceptance criteria, tests, API/event/data review, observability, and documentation.

### Architecture change

Changes module ownership, dependency direction, deployable topology, primary technology, consistency model, or critical pattern. It requires an ADR.

### Security/privacy change

Touches authentication, authorization, store/customer isolation, admin access, uploads, credentials, sensitive data, analytics fields/consent, reservation correctness, or logs. It requires threat review and a security-aware reviewer.

### Operational change

Changes infrastructure, migrations, CI/CD, secrets, alerts, backups, scaling, or runbooks. It requires platform review and rollout/rollback evidence.

## Branch and change workflow

- Protect `main` and `develop`; changes arrive through pull requests.
- Use short-lived `feature/*` branches from current `develop`.
- Keep a pull request focused on one coherent outcome.
- Rebase or update safely according to repository policy before final merge.
- Do not mix broad mechanical formatting with behavior changes.
- Feature flags may permit incremental integration, but incomplete behavior must be safely unreachable and flags must have removal dates.
- Never commit secrets or real customer/store data.

Recommended branch names:

- `feature/issue-short-name`
- `release/version`
- `hotfix/issue-short-name`

Exact ticket prefixes may be added when the issue tracker is selected.

The authoritative branching, rebasing, merge, tag, and release procedure is [Git Workflow](git-workflow.md). `main` is production-ready history, `develop` integrates the next release, and release exposure remains controlled by compatible deployment and short-lived feature flags.

## Commit standards

Use concise imperative commits that describe intent. Conventional Commit-style prefixes are recommended:

- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`
- `perf:`
- `build:`
- `ci:`
- `chore:`

Commits should be reviewable and pass relevant checks. Do not hide generated artifacts, migration changes, or mass formatting inside an unrelated commit.

## Architecture rules for contributors

- Put behavior in the owning feature module.
- Domain and application layers do not import frameworks/infrastructure.
- Routers do not query the database or implement business state changes.
- Modules do not import another module's ORM models.
- Use module facades for immediate cross-module coordination and events for post-commit side effects.
- Keep shared kernel small and business-neutral.
- Repositories express domain queries, tenant scope, and concurrency intent; avoid universal CRUD repositories.
- PostgreSQL enforces critical invariants.
- Redis, Meilisearch, PostHog, and Sentry are never systems of record.
- Background jobs are idempotent and safe under duplicate delivery.
- Avoid new infrastructure or abstractions without demonstrated need.
- Do not split modules into microservices.

## Adding or changing an API

1. Cite the functional requirement and actors.
2. Change `docs/api/openapi.yaml` and examples before implementation.
3. Define authorization and tenant ownership.
4. Design resource/command semantics and state conflicts.
5. Define request/response and stable problem codes.
6. Define pagination, idempotency, concurrency, caching, and rate limiting.
7. Run OpenAPI lint and breaking-change review.
8. Regenerate clients reproducibly.
9. Implement FastAPI and pass semantic contract conformance.
10. Update API changelog for client-visible behavior.
11. Add contract, authorization, validation, and end-to-end tests.

Never expose an ORM model as an API response or add private stock to a public representation.

## Adding or changing a database model

1. Confirm the owning module and aggregate/invariant.
2. Classify every new field and define retention.
3. Add database constraints and indexes that match access patterns.
4. Generate then manually review the Alembic migration.
5. Use expand/migrate/contract for incompatible or large changes.
6. Test upgrade from a production-like schema/data shape.
7. Test repository behavior with real PostgreSQL.
8. Explain locking, backfill, downtime, rollback/roll-forward, and mixed-version compatibility in the PR.
9. Update the data dictionary.

Never make manual production schema or data changes outside the approved migration/administrative process.

Mutable aggregate changes explicitly decide whether the monotonic version is checked. Deletion changes follow the lifecycle policy; adding `deleted_at` generically or cascading a business ledger is not accepted.

## Adding an event or Celery task

Document:

- owning producer and consumers;
- stable name and schema version;
- minimal classified payload;
- transaction/outbox relationship;
- idempotency/deduplication key;
- retryable and terminal failures;
- timeouts, backoff, queue, and priority;
- ordering assumptions;
- observability and replay procedure;
- compatibility during rolling deployment.

Tests deliver the event/task more than once and out of expected timing. Never pass ORM objects or secrets as task payloads.

## Adding analytics

Before emitting a PostHog event:

- add it to the tracking plan;
- define the product question and metric owner;
- use a stable name and property schema;
- classify each property;
- exclude search text or identifiers if they can contain personal/sensitive data unless explicitly approved and transformed;
- define consent and retention behavior;
- test that failure does not block the workflow;
- prevent accidental duplicate events where the metric requires uniqueness.

Sentry, operational metrics, audit logs, and PostHog have different purposes and must not be substituted for each other.

## Security and privacy checklist

For every change ask:

- Can one customer or store access another's object, list, count, export, media, or aggregate?
- Can a staff user perform an owner/admin action?
- Can a client set protected fields through mass assignment?
- Can retries, races, or delayed workers duplicate an effect?
- Can input cause SQL/command/template injection, XSS, path traversal, or SSRF?
- Does the change log or transmit credentials, signed URLs, PII, exact stock, or request bodies?
- Does caching mix tenants or retain revoked access?
- Do uploads remain type/size/ownership constrained?
- Is account/resource existence leaked?
- Are rate limits and abuse costs appropriate?
- Does deletion respect retention, references, audit, and backups?

Security-sensitive changes require negative tests, not only successful use cases.

## Testing expectations

Run the smallest fast suite during development and the complete required suite before review. Tests must cover:

- pure domain rules and invalid states;
- application authorization and coordination;
- PostgreSQL constraints, repositories, locks, and migrations;
- Redis/RabbitMQ/Meilisearch/R2/provider adapters where relevant;
- OpenAPI and event contracts;
- tenant isolation for object and collection operations;
- accessibility for changed UI;
- critical end-to-end behavior;
- load/concurrency for performance-sensitive or integrity-sensitive changes.

A fix includes a regression test when feasible. Do not merge by repeatedly rerunning a flaky test.

The standard local gate is pre-commit with Ruff, ESLint/Prettier, secret and contract syntax checks. CI adds strict Pyright/TypeScript, pytest/Vitest, PostgreSQL integration, RabbitMQ redelivery, Playwright/axe, OpenAPI conformance, migration, image, OpenTofu, dependency, performance, and security suites according to risk.

## Documentation expectations

Update documentation in the same pull request when changing:

- product scope or behavior;
- requirement acceptance;
- API/error/event contract;
- module ownership/dependencies;
- database fields, classification, or retention;
- configuration/environment variables;
- deployment, migration, backup, recovery, or on-call behavior;
- security controls/threat model;
- analytics tracking;
- user or operator workflow.

Documentation uses clear present/future requirements, stable IDs, valid relative links, and no real secret or customer data.

## Pull request description

Every substantial PR should contain:

```text
Outcome:
Requirements:
Scope and non-goals:
Architecture/module ownership:
API/event/data changes:
Security/privacy/tenant impact:
Migration and compatibility:
Observability/analytics:
Tests and evidence:
Rollout:
Rollback or roll-forward:
Documentation:
Risks/open decisions:
```

This is a review template, not application code. Remove sections only when genuinely not applicable and state why for high-risk categories.

## Review expectations

### Author

- self-review the diff;
- remove debug output, unused code, expired TODOs, and accidental generated changes;
- provide focused evidence, not only “tests pass”;
- respond to review with changes or concrete reasoning;
- avoid resolving substantive threads without agreement.

### Reviewer

Review for:

- correctness and scope;
- module boundaries and simplicity;
- authorization and privacy;
- transaction/concurrency/idempotency;
- contract and migration compatibility;
- failure behavior and observability;
- accessibility and performance;
- tests that would fail if the behavior regressed;
- operational rollout and recovery.

Approval means the reviewer believes the change is safe to own in production, not merely stylistically acceptable.

Required specialized review:

| Change | Required reviewer |
|---|---|
| Auth, Admin, permissions, tenancy, uploads, reservation locks | Security-aware owner |
| Alembic or critical query/index | Backend/data owner |
| Infrastructure, CI/CD, secrets, backups | Platform owner |
| Public API/event breaking risk | API/module owners and affected frontend owner |
| Accessibility/design-system | Frontend/accessibility owner |
| Analytics schema/PII/consent | Product analytics/privacy owner |
| Product scope/requirement | Product owner |

## Merge policy

Merge only when:

- required approvals are present;
- protected CI checks pass;
- no unresolved blocking conversation remains;
- required documentation/migrations/generated contracts are included;
- security findings meet policy;
- deployment compatibility is known.

Use squash merge with a Conventional Commit title for `feature/*` pull requests into `develop`. Merge approved `release/*` and `hotfix/*` pull requests into `main` with an explicit merge commit, tag that commit, and synchronize `main` back to `develop` as defined in [Git Workflow](git-workflow.md). Release automation derives a changelog and Semantic Version for external contracts; application deployments retain their commit SHA and release identifier even when they do not publish a package.

## Architecture Decision Records

Create an ADR when a decision:

- changes a mandated technology or architecture;
- creates a new shared/cross-module pattern;
- changes consistency, ownership, or transaction boundaries;
- introduces an external provider or significant dependency;
- has meaningful irreversible cost or migration;
- rejects a plausible alternative future engineers will reconsider.

An ADR includes status, context, decision, alternatives, consequences, security/privacy, rollout, rollback, and owner/date. Supersede old ADRs; do not rewrite accepted history invisibly.

## Handling incidents and urgent changes

- Follow the incident command and production-access runbooks.
- Keep emergency changes minimal and reviewable.
- Do not bypass audit, secrets handling, or backup checks unless the incident commander explicitly records why.
- Prefer a kill switch/rollback when safe.
- Add full tests, documentation, and follow-up cleanup immediately after stabilization.
- Conduct a blameless review focused on system improvements.

## Reporting a security issue

Do not open a public issue containing exploit details, credentials, or personal data. Use the private security contact defined in the future repository security policy. If no channel exists yet, contact the designated security owner directly and preserve evidence without broad distribution.

## Contributor completion checklist

- The change directly supports an approved requirement.
- Product boundaries remain intact.
- Correct module and dependency direction are used.
- Authorization and tenant isolation are explicit.
- Transactions, retries, and concurrency are safe.
- Public/private data separation is preserved.
- API/event/schema changes are compatible and documented.
- Tests cover success and failure.
- Logs, Sentry, PostHog, and audit usage are correct.
- Accessibility and mobile behavior are verified.
- Migration, deployment, and recovery are ready.
- Documentation and ownership are current.
