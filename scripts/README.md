# Development scripts

The bootstrap scripts validate Docker, preserve an existing `.env.development`, build and start the complete Compose environment, and run the containerized verifier.

- Linux/macOS: `./scripts/bootstrap.sh`
- Windows PowerShell: `.\scripts\bootstrap.ps1`
- Verification only: `docker compose --profile tools run --rm verify`

Scripts are safe to rerun. They do not delete named volumes. `make clean` is the explicit destructive command for removing local service data.
