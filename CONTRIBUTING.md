# Contributing to Fashion Network

Thank you for contributing. The documentation in [`docs/`](docs/README.md) is the source of truth. Every change must preserve Fashion Network as a searchable inventory network—not an e-commerce merchant, payment processor, warehouse, or fulfillment operator.

## Before starting

1. Read the documentation map and the requirements relevant to the change.
2. Confirm that an issue or approved work item defines the outcome and acceptance criteria.
3. Choose the correct branch type from [`docs/git-workflow.md`](docs/git-workflow.md).
4. Install the pinned Python and Node.js dependencies.
5. Never use real credentials, customer data, or store data in development or tests.

## Branch strategy

The repository uses a controlled GitFlow-inspired strategy:

| Branch      | Purpose                                             | Created from     | Merged into                            |
| ----------- | --------------------------------------------------- | ---------------- | -------------------------------------- |
| `main`      | Production-ready, tagged history                    | N/A              | N/A                                    |
| `develop`   | Integration for the next release                    | `main` initially | `main` through a release PR            |
| `feature/*` | Features, fixes, docs, and routine engineering work | `develop`        | `develop`                              |
| `release/*` | Release hardening only                              | `develop`        | `main`, then synchronized to `develop` |
| `hotfix/*`  | Urgent production correction                        | `main`           | `main`, then synchronized to `develop` |

Keep working branches short-lived. Direct pushes to `main` and `develop` are prohibited after branch protection is enabled. See the workflow guide for naming, synchronization, tagging, and merge details.

## Coding and documentation standards

- Follow [`docs/08-coding-standards.md`](docs/08-coding-standards.md), Clean Architecture, SOLID, and feature ownership.
- Do not change architecture or a mandatory technology without an approved ADR.
- Keep pull requests focused on one coherent outcome.
- Update contracts and documentation in the same pull request as the behavior they govern.
- Do not mix broad formatting changes with functional changes.
- Do not suppress quality checks without an issue, owner, and expiry.

## Commit standards

All commit subjects and squash-merge titles follow Conventional Commits:

```text
<type>(optional-scope): <imperative summary>
```

Supported types and examples:

- `feat: add store search filters`
- `fix: prevent stale inventory projection`
- `docs: clarify reservation terminology`
- `test: cover concurrent stock holds`
- `refactor: isolate search adapter mapping`
- `perf: reduce inventory query count`
- `ci: cache pnpm dependencies`
- `build: pin Python build tooling`
- `chore: refresh repository metadata`

Use lower-case types, an imperative summary, and no trailing period. Add `!` and a `BREAKING CHANGE:` footer only for an approved breaking change. Reference issues in footers, for example `Refs: #123`.

Commitlint enforces this contract in the local `commit-msg` hook and CI. Run `corepack pnpm install` once, then configure the repository hooks with:

```text
git config core.hooksPath .githooks
```

## Local quality checks

Run the checks relevant to the change. Before requesting review, the default complete gate is:

```text
make lint
make typecheck
make test
make build
corepack pnpm format:check
```

CI is authoritative. A passing local run does not replace review or protected checks.

## Pull request process

1. Rebase a feature branch onto the latest `develop`; rebase release or hotfix branches only before they are shared.
2. Push the branch and open a pull request using the repository template.
3. Link requirements/issues and explain scope, tests, risk, rollout, and rollback where applicable.
4. Obtain CODEOWNERS and specialized approvals.
5. Resolve review feedback and keep all required CI checks green.
6. Squash-merge routine `feature/*` pull requests into `develop` with a Conventional Commit title.
7. Merge approved `release/*` and `hotfix/*` pull requests into `main` with a merge commit so the release boundary is explicit, create an annotated tag, then synchronize `main` back into `develop`.

Never force-push `main`, `develop`, or any branch another contributor is actively using. Never merge with unresolved security findings or failing required checks.

## Review priorities

Reviewers evaluate scope, correctness, ownership boundaries, authorization and tenant isolation, data integrity, retry/concurrency safety, compatibility, observability, accessibility, operational safety, tests, and documentation. Approval means the change is safe to own in production.

## Security

Follow [`SECURITY.md`](SECURITY.md). Never report a suspected vulnerability in a public issue.
