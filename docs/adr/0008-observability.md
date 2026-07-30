# ADR 0008: Layered Observability

- Date: 2026-07-30
- Status: Accepted

## Context

Production diagnosis requires complementary signals: events and context, aggregate behavior, causal request flow, and actionable exceptions. No single signal answers every operational question.

## Decision

Use a layered observability strategy:

- structured application logs with correlation identifiers;
- Prometheus-compatible metrics for service and dependency health;
- OpenTelemetry traces exported through a Collector;
- Sentry for exception aggregation and release-aware error reporting;
- Grafana for local and operator-facing metric visualization;
- health endpoints separated into liveness, startup, and readiness semantics.

Metrics and administration endpoints are private infrastructure surfaces. Production alerting, retention, sampling, and personally identifiable information controls are environment-specific operational configuration.

## Alternatives considered

- A single proprietary observability suite: simpler integration, but creates broader lock-in before production requirements and cost are known.
- Logs only: rejected because trends, saturation, service objectives, and request causality remain difficult to assess.
- A self-hosted full production monitoring stack by default: rejected because ongoing platform operations are not justified for the startup foundation.

## Consequences

- Incidents can be investigated across logs, metrics, traces, and errors.
- Correlation fields and naming conventions must remain consistent.
- Multiple signals add dependencies, storage, retention, alert-tuning, and cost considerations.
- Local Prometheus, Grafana, and Collector containers validate integration; production may use managed compatible providers without changing application boundaries.
