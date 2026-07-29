# Git Workflow

## Purpose

This document is the authoritative branch, commit, merge, tag, and release workflow for Fashion Network. It supplements the architecture contribution guide without changing the modular-monolith architecture or product scope.

## Branch model

| Branch pattern | Role | Source | Pull request target | Lifetime |
|---|---|---|---|---|
| `main` | Production-ready releases | Release or hotfix PR | N/A | Permanent |
| `develop` | Integrated next release | `main` | N/A | Permanent |
| `feature/<issue>-<slug>` | Approved feature, fix, docs, test, or tooling work | `develop` | `develop` | Short-lived |
| `release/<version>` | Stabilization, versioning, and release notes | `develop` | `main` | Until release |
| `hotfix/<issue>-<slug>` | Urgent production correction | `main` | `main` | Until hotfix |

Protect `main` and `develop`. Require pull requests, CODEOWNERS review, passing lint/test/build checks, resolved conversations, no force pushes, no deletions, and no administrator bypass except a documented incident procedure.

## Creating a feature branch

Update local references and start from `develop`:

```text
git fetch --prune origin
git switch develop
git pull --ff-only origin develop
git switch -c feature/123-search-filters
```

Use `feature/*` for routine changes, including documentation and CI work, so that the release flow stays predictable. Keep one coherent outcome per branch.

## Committing

Review and stage intentionally:

```text
git status --short
git diff
git add path/to/file
git diff --cached
git commit -m "feat(search): add category filter contract"
```

Commit subjects use Conventional Commits and the types `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `ci`, `build`, or `chore`. The local `commit-msg` hook and CI run commitlint.

Do not stage with `git add .` without reviewing the complete diff. Never commit secrets, `.env` files, personal data, production exports, editor caches, dependency directories, or generated build output.

## Rebasing

Before opening or updating a feature pull request:

```text
git fetch origin
git rebase origin/develop
```

Resolve conflicts one file at a time, run relevant checks, then use `git rebase --continue`. Use `git rebase --abort` if the resolution is unsafe. After rebasing a branch that only you own, update it with:

```text
git push --force-with-lease
```

Never rebase `main`, `develop`, or a shared release/hotfix branch. `--force-with-lease` is mandatory when a force update is genuinely needed because it refuses to overwrite unexpected remote work.

## Merging pull requests

- Squash-merge `feature/*` into `develop`. The pull request title becomes a valid Conventional Commit.
- Create `release/<version>` from `develop`. Permit only release notes, version metadata, and stabilization fixes.
- Merge a release PR into `main` with a merge commit after all release gates pass.
- Merge a `hotfix/*` PR into `main` with a merge commit after focused production validation.
- After either mainline merge, synchronize `main` back into `develop` promptly through a pull request or controlled merge. Resolve the same change only once.
- Delete remote working branches after successful merge.

Do not merge locally into protected branches or bypass required checks.

## Tagging

Use annotated, signed tags for production releases when signing is configured:

```text
git switch main
git pull --ff-only origin main
git tag -s v1.2.0 -m "Fashion Network v1.2.0"
git push origin v1.2.0
```

Until signing is configured, use `git tag -a`. Phase or milestone tags such as `phase-1.1` identify engineering baselines; production releases use Semantic Versioning (`vMAJOR.MINOR.PATCH`). Never move or silently replace a published tag.

## Release procedure

1. Create `release/vX.Y.Z` from tested `develop`.
2. Freeze feature scope and complete release notes, compatibility review, migration review, security checks, and rollback/roll-forward evidence.
3. Open the release pull request to `main` and obtain required approvals.
4. Merge with an explicit merge commit after protected checks pass.
5. Create and verify an annotated or signed `vX.Y.Z` tag on the merge commit.
6. Promote the exact immutable artifacts built from that commit.
7. Synchronize `main` back to `develop`.
8. Publish release notes and monitor the rollout.

Hotfixes follow the same verification, tagging, and synchronization rules with the smallest safe scope.

## Recommended Git aliases

Aliases are optional and developer-local. Review each command before adding it:

```text
git config --global alias.st "status --short --branch"
git config --global alias.co switch
git config --global alias.cob "switch -c"
git config --global alias.br branch
git config --global alias.last "log -1 --stat"
git config --global alias.lg "log --graph --decorate --oneline --all"
git config --global alias.unstage "restore --staged --"
git config --global alias.sync "!git fetch --prune && git rebase origin/develop"
```

`git sync` is for a private feature branch only. Do not use it while on `main`, `develop`, or a shared branch. Repository documentation must never require personal global aliases.

## Recovery and safety

- Use `git reflog` to locate recoverable commits after an accidental local branch operation.
- Prefer `git revert` for changes already shared or released.
- Never use destructive reset or force-push on protected branches.
- Rotate exposed credentials even if the committing history is later cleaned.
- Ask a maintainer before rewriting shared history.
