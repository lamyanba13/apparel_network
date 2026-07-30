# Monitoring

Phase 1.5 provides the local `observability` Compose profile:

- OpenTelemetry Collector `0.157.0` accepts OTLP/gRPC and OTLP/HTTP and writes to
  a debug exporter, so no external collector is required;
- Prometheus `3.13.0` scrapes the backend and evaluates the version-controlled
  foundation alert rules;
- Grafana `13.1.0` provisions Prometheus as its default data source.

Start it with:

```text
docker compose --profile observability up --detach
```

Configuration is read-only in containers; Prometheus and Grafana data use named
development volumes. Every published port is loopback-only. This is a local
diagnostic stack, not the approved production telemetry backend. See
`docs/observability.md`.
