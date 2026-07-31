# Production Deployment Checklist

## Identity freeze gate

- [ ] Complete every operational-verification item in the
      [Phase 2.6 Identity freeze](phase-2.6-identity-freeze.md).
- [ ] Confirm the active signing-key type matches the configured JWT algorithm
      and every published `kid` resolves to the intended public key.
- [ ] Confirm Identity RFC 9457 responses, bearer declarations, rate limits,
      cleanup execution, event scrubbing, metrics, and alerts in staging.
- [ ] Treat any dependency advisory affecting production Identity execution as
      a release blocker unless Security records a time-bounded exception.

## Release identity and approvals

- [ ] Change list, commit SHA, immutable image digests, SBOMs, scan results, owner, and incident contact are recorded.
- [ ] Required reviews and protected CI checks pass.
- [ ] Rollback/roll-forward decision, schema/event compatibility, and watch window are approved.
- [ ] No Phase 2 feature is accidentally enabled.

## Infrastructure and security

- [ ] OpenTofu plan is reviewed and applied through protected OIDC automation.
- [ ] networks expose only approved edge routes; stateful services, `/metrics`, management UIs, and collectors remain private.
- [ ] TLS, trusted proxy/client-IP handling, body/header/time limits, CORS, trusted hosts, and security headers pass external checks.
- [ ] secret-manager values and workload identities are present, least-privilege, environment-specific, and rotation-ready.
- [ ] `SECURITY_CHECKLIST.md` is signed off; no unaccepted exploitable Critical/High finding remains.
- [ ] CPU, memory, connections, disk, and provider limits match `docs/resource-limits.md` or an approved measured value.

## Data and dependencies

- [ ] PostgreSQL backup/PITR is current and restore evidence is within the required quarter.
- [ ] Alembic has one expected head and the expansion migration was tested against a production-like shape.
- [ ] RabbitMQ topology/TLS/private access, Redis ephemeral policy, Meilisearch settings/rebuild, and R2 private policy are verified.
- [ ] dependency audits and container scans reflect the exact release artifacts.

## Observability and readiness

- [ ] production structured logs, OpenTelemetry export, Prometheus scrape, Grafana dashboards, and Sentry release mapping work.
- [ ] PII/log/Sentry scrubbing tests pass.
- [ ] alerts have tested routing, primary/backup owners, and runbook links.
- [ ] `/health/live` checks process only; `/health/startup` confirms initialization; `/health/ready` checks all required dependencies.
- [ ] liveness/readiness intervals and failure thresholds avoid restart storms.

## Rollout

- [ ] apply backward-compatible migrations with the dedicated migration identity;
- [ ] deploy a canary/first replica and verify startup timing, probes, errors, latency, resources, pool, and dependencies;
- [ ] expand gradually while monitoring SLO/error burn, RabbitMQ/worker state, and provider saturation;
- [ ] verify Swagger is disabled and `/metrics` is not public;
- [ ] annotate dashboards and Sentry with the deployment.

## Post-deployment

- [ ] smoke and negative network-exposure checks pass.
- [ ] no regression remains through the approved watch window.
- [ ] queue age, errors, saturation, and dependency readiness are healthy.
- [ ] release notes, known limitations, and follow-up owners are recorded.
- [ ] rollback/forward artifacts remain available through the release window.
