# Development environment

The root `docker-compose.yml`, `.env.development`, and `scripts/verify_environment.py` own the Phase 1.2 local runtime. See [`docs/local-development.md`](../../docs/local-development.md).

Local dependencies use named volumes, a dedicated loopback host-access network, health checks, restart policies, bounded logs, and the internal data network.
