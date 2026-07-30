# Infrastructure

Phase 1.5 retains the complete local Docker Compose runtime and adds an optional
business-neutral observability profile while preserving the approved production architecture.

- `docker/`: container conventions and future shared support files.
- `nginx/`: development-only reverse proxy image and host-based routing.
- `monitoring/`: OpenTelemetry Collector, Prometheus scrape/alerts, and Grafana
  provisioning for local diagnostics.
- `development/`: local environment notes.
- `production/`: production boundary; no cloud deployment is created in Phase 1.2.
- `tofu/`: future OpenTofu modules and environment composition.

The root `docker-compose.yml` is the only local service definition.
Production continues to use managed telemetry storage and private managed
stateful services rather than this local profile.
