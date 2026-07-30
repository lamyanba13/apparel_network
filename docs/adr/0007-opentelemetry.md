# ADR 0007: OpenTelemetry for Distributed Telemetry

- Date: 2026-07-30
- Status: Accepted

## Context

HTTP requests, database operations, cache access, broker interactions, and background jobs need correlation without binding application instrumentation to one monitoring vendor.

## Decision

Use OpenTelemetry APIs and semantic conventions for traces and correlated telemetry. Export through an OpenTelemetry Collector, with instrumentation enabled and sampled by environment configuration.

Telemetry must not contain secrets, authentication tokens, raw personal data, or uncontrolled high-cardinality fields. Instrumentation failure must not fail a customer request.

## Alternatives considered

- Vendor-specific tracing SDKs only: rejected because they create avoidable lock-in at instrumentation points.
- Custom trace propagation and export: rejected because it duplicates standards and ecosystem tooling.
- No tracing: rejected because asynchronous jobs and multiple infrastructure dependencies are difficult to diagnose from logs alone.

## Consequences

- Instrumentation remains portable across compatible backends.
- The Collector provides a policy and export boundary.
- Libraries, propagation, sampling, and Collector configuration add operational overhead.
- Trace volume and attribute cardinality require cost and performance governance.
