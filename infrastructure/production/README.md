# Production environment

Production infrastructure remains provider-dependent and intentionally absent
from Phase 1.5. The local Compose, Nginx, MinIO, Prometheus, Grafana, and debug
collector containers are not production specifications. Production requires
OpenTofu, private networking, managed services/telemetry, Cloudflare R2,
secret-manager injection, backups, immutable images, and the protected
deployment workflow in `docs/production-deployment-checklist.md`.
