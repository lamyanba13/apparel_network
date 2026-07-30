# Development scripts

The bootstrap scripts validate Docker, preserve an existing `.env.development`,
build and start the complete core Compose environment, apply the current
Alembic head, and run the Phase 1.5 probe/metrics-aware verifier.

- Linux/macOS: `./scripts/bootstrap.sh`
- Windows PowerShell: `.\scripts\bootstrap.ps1`
- Verification only: `docker compose --profile tools run --rm verify`
- Optional monitoring: `docker compose --profile observability up --detach`
- Migrations only: `docker compose run --rm backend alembic upgrade head`

Scripts are safe to rerun. They do not delete named volumes. `make clean` is the explicit destructive command for removing local service data.
