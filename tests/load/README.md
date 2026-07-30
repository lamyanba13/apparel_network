# Load-test examples

These scripts exercise only Phase 1.5 infrastructure endpoints. They are examples, not automated benchmarks, and must never target production without an approved test plan and owner.

## k6

Start the local stack, then run:

```text
k6 run -e BASE_URL=http://127.0.0.1:8000 tests/load/k6.js
```

The one-minute profile ramps to ten virtual users and checks the public-read latency objectives from the non-functional requirements. Change traffic, duration, dataset, and thresholds only in a reviewed scenario.

## Locust

Install Locust in an isolated tool environment and run:

```text
pipx run locust -f tests/load/locustfile.py --host http://127.0.0.1:8000
```

Open `http://127.0.0.1:8089`, choose a bounded local user count, and stop the run if dependency saturation affects other work.

## Reporting

Every result must record commit SHA, environment, CPU/memory limits, dataset size, concurrency, duration, cache state, request mix, error rate, p50/p95/p99 latency, dependency saturation, and any correctness failures. Results from a developer laptop are development baselines, not production capacity claims.
