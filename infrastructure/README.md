# Infrastructure foundation

Phase 1.1 reserves infrastructure ownership without creating Docker images, proxy configuration, monitoring resources, cloud resources, or production services.

- `docker/`: future container support files.
- `nginx/`: optional proxy configuration only if the selected hosting platform requires it.
- `monitoring/`: future OpenTelemetry, dashboard, alert, and synthetic-check definitions.
- `development/`: development-environment runtime composition.
- `production/`: production-environment runtime composition.
- `tofu/`: future OpenTofu modules and environment composition.

