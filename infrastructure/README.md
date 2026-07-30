# Infrastructure

Phase 1.2 implements the complete local Docker Compose runtime while preserving the approved production architecture.

- `docker/`: container conventions and future shared support files.
- `nginx/`: development-only reverse proxy image and host-based routing.
- `monitoring/`: future OpenTelemetry, dashboard, alert, and synthetic-check definitions.
- `development/`: local environment notes.
- `production/`: production boundary; no cloud deployment is created in Phase 1.2.
- `tofu/`: future OpenTofu modules and environment composition.

The root `docker-compose.yml` is the only local service definition.
