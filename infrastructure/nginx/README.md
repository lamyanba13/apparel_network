# Development Nginx gateway

The Phase 1.2 gateway provides local host-based routing and WebSocket forwarding for framework hot reload:

- `localhost` → public frontend;
- `dashboard.localhost` → dashboard;
- `api.localhost` → FastAPI;
- `localhost/healthz` → proxy liveness.

This image is a local-development convenience. Production ingress remains owned by the selected managed platform unless a later ADR demonstrates the need for Nginx.
