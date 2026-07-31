# Phase 1.5 Dependency and Container Security Report

## Scope and date

This report records the Phase 1.5 foundation audit performed on 2026-07-30. It covers the locked Python and Node.js dependency graphs plus the deployable backend, frontend, dashboard, and Nginx images. It is evidence for the development foundation, not a substitute for the production deployment security gate.

## Results

| Scope                      | Command or control                       | Result                                        |
| -------------------------- | ---------------------------------------- | --------------------------------------------- |
| Python environment         | `pip-audit --local`                      | Pass: no known vulnerabilities                |
| Node.js production graph   | `pnpm audit --prod --audit-level high`   | Pass: no known vulnerabilities                |
| Node.js peer constraints   | `pnpm peers check`                       | Pass: no peer dependency issues               |
| Full Node.js graph         | `pnpm audit --audit-level high`          | One accepted development-only exception below |
| Backend production image   | Trivy 0.70.0, fixed HIGH/CRITICAL policy | Pass                                          |
| Frontend production image  | Trivy 0.70.0, fixed HIGH/CRITICAL policy | Pass                                          |
| Dashboard production image | Trivy 0.70.0, fixed HIGH/CRITICAL policy | Pass                                          |
| Nginx production image     | Trivy 0.70.0, fixed HIGH/CRITICAL policy | Pass                                          |

The production images are multi-stage artifacts. Poetry, test tools, compilers, npm, Corepack, and Yarn do not ship in the relevant final runtime images. Image scans use exported read-only archives and do not mount the host Docker socket into the scanner.

## Development-only exception

| Field                       | Value                                                                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Advisory                    | `GHSA-mh99-v99m-4gvg`                                                                                                                                                     |
| Package                     | `brace-expansion`                                                                                                                                                         |
| Affected version            | `5.0.6` through the ESLint dependency graph                                                                                                                               |
| Severity                    | High                                                                                                                                                                      |
| Exposure                    | Development and CI lint tooling only; absent from both standalone Node production images and the production dependency audit                                              |
| Risk                        | A malicious, attacker-controlled glob supplied to the lint tool could cause memory exhaustion                                                                             |
| Mitigation                  | Lint only trusted repository paths and version-controlled configuration; use ephemeral bounded CI runners; do not expose ESLint as a service or process untrusted uploads |
| Reason not force-overridden | Forcing `brace-expansion` 5.0.8 into the current ESLint graph causes a runtime incompatibility and prevents linting                                                       |
| Owner                       | Platform Engineering                                                                                                                                                      |
| Review cadence              | On every lockfile update and at least monthly                                                                                                                             |
| Expiry                      | 2026-08-30                                                                                                                                                                |
| Closure condition           | Upgrade to an upstream ESLint dependency graph that resolves to a patched compatible release                                                                              |
| Approval status             | Accepted for Phase 1.5 development only; production approval is not granted or required because the package is absent from production artifacts                           |

If the exception expires before an upstream-compatible update is available, Platform Engineering must renew it with Security review or block affected CI usage. A newly disclosed production dependency finding blocks release until fixed or formally accepted under the security policy.

## Repeatable audit gates

CI runs Python and production Node dependency audits, CodeQL for Python and JavaScript/TypeScript, production image builds, and fixed HIGH/CRITICAL container scans. Scheduled security checks run weekly in addition to pull request and protected-branch checks.

Release evidence must retain the lockfile revisions, image digests, scanner version/database timestamp, scan policy, accepted exceptions, and workflow run URL.

## Phase 2.6 Identity freeze revalidation

The Phase 2.6 gate rechecks the Python environment, production Node graph, and
lockfile consistency without changing application dependency versions. No
project dependency-license allowlist or denylist is currently documented. The
first local Python scan found advisories
only in an out-of-date host Poetry 2.1.3 installation and its Dulwich 0.22.8
dependency. Neither is part of the application runtime graph. The local tool was
aligned with the backend Docker build pin (Poetry 2.4.1, Dulwich 1.2.12), which
exceeds the advisory fix versions; the repository lock remained valid.

The development-only `brace-expansion` exception remains time-bounded to
2026-08-30 and must not be renewed implicitly. Command results are recorded in
the Phase 2.6 delivery evidence; a newly discovered production advisory is a
release blocker.

## Phase 3.4 Store Media additions

Phase 3.4 adds three production dependencies under the existing object-storage
and upload decisions:

| Package            | Purpose                                                  | Declared license |
| ------------------ | -------------------------------------------------------- | ---------------- |
| `minio`            | Tested S3-compatible MinIO/R2 storage adapter            | Apache-2.0       |
| `Pillow`           | Decoded image validation and trusted metadata extraction | MIT-CMU          |
| `python-multipart` | Bounded FastAPI multipart request parsing                | Apache-2.0       |

No CDN, media transformation, background-job, OCR, AI, video, or generic upload
framework dependency was introduced. The Poetry lockfile is authoritative and
the standard production vulnerability gate applies to the updated graph.
