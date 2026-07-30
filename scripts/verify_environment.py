from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class VerificationError(RuntimeError):
    """Describe one local-environment verification failure."""


@dataclass(frozen=True)
class Check:
    name: str
    run: Callable[[], None]


def load_environment(path: Path) -> None:
    """Load an env file without overriding explicitly supplied process values."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def require_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise VerificationError(f"required environment variable {name} is missing")
    return value


def fetch(
    url: str,
    *,
    expected_text: str | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            if not 200 <= response.status < 300:
                raise VerificationError(f"{url} returned HTTP {response.status}")
    except (OSError, urllib.error.URLError) as error:
        raise VerificationError(f"{url} is unavailable: {error}") from error

    if expected_text and expected_text.encode() not in body:
        raise VerificationError(f"{url} did not contain {expected_text!r}")
    return body


def basic_auth(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def verify_postgres(host: str) -> None:
    try:
        import psycopg
    except ImportError as error:
        raise VerificationError("psycopg is not installed; run verification in Docker") from error

    database = require_environment("POSTGRES_DB")
    user = require_environment("POSTGRES_USER")
    password = require_environment("POSTGRES_PASSWORD")
    try:
        with psycopg.connect(
            host=host,
            port=5432,
            dbname=database,
            user=user,
            password=password,
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW server_encoding")
                encoding = cursor.fetchone()
                cursor.execute("SHOW timezone")
                timezone = cursor.fetchone()
    except Exception as error:
        raise VerificationError(f"PostgreSQL connection failed: {error}") from error

    if not encoding or encoding[0] != "UTF8":
        raise VerificationError(f"PostgreSQL encoding is not UTF8: {encoding}")
    if not timezone or timezone[0] != "UTC":
        raise VerificationError(f"PostgreSQL timezone is not UTC: {timezone}")


def verify_redis(host: str) -> None:
    try:
        import redis
    except ImportError as error:
        raise VerificationError("redis client is not installed; run verification in Docker") from error

    password = require_environment("REDIS_PASSWORD")
    try:
        client = redis.Redis(
            host=host,
            port=6379,
            password=password,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        if client.ping() is not True:
            raise VerificationError("Redis PING did not return true")
    except Exception as error:
        raise VerificationError(f"authenticated Redis PING failed: {error}") from error


def verify_rabbitmq(base_url: str) -> None:
    headers = basic_auth(
        require_environment("RABBITMQ_USER"),
        require_environment("RABBITMQ_PASSWORD"),
    )
    payload = json.loads(
        fetch(f"{base_url}/api/health/checks/alarms", headers=headers)
    )
    if payload.get("status") != "ok":
        raise VerificationError(f"RabbitMQ alarm check is not healthy: {payload}")


def verify_meilisearch(base_url: str) -> None:
    payload = json.loads(fetch(f"{base_url}/health"))
    if payload.get("status") != "available":
        raise VerificationError(f"Meilisearch is not available: {payload}")


def verify_minio(base_url: str, marker: Path | None) -> None:
    fetch(f"{base_url}/minio/health/ready")
    if marker is not None and not marker.exists():
        raise VerificationError("MinIO is healthy but bucket initialization marker is absent")


def verify_flower(base_url: str) -> None:
    headers = basic_auth(
        require_environment("FLOWER_USER"),
        require_environment("FLOWER_PASSWORD"),
    )
    fetch(f"{base_url}/", headers=headers)
    workers: dict[str, Any] = json.loads(
        fetch(f"{base_url}/api/workers?refresh=1", headers=headers)
    )
    if not workers:
        raise VerificationError("Flower is healthy but reports no Celery workers")


def build_checks(inside_compose: bool) -> list[Check]:
    if inside_compose:
        postgres_host = "postgres"
        redis_host = "redis"
        backend_url = "http://backend:8000"
        frontend_url = "http://frontend:3000"
        dashboard_url = "http://dashboard:3000"
        rabbitmq_url = "http://rabbitmq:15672"
        meilisearch_url = "http://meilisearch:7700"
        minio_url = "http://minio:9000"
        flower_url = "http://flower:5555"
        mailpit_url = "http://mailpit:8025"
        nginx_url = "http://nginx"
        minio_marker: Path | None = Path("/state/minio-initialized")
    else:
        postgres_host = "127.0.0.1"
        redis_host = "127.0.0.1"
        backend_url = "http://127.0.0.1:8000"
        frontend_url = "http://127.0.0.1:3000"
        dashboard_url = "http://127.0.0.1:3001"
        rabbitmq_url = "http://127.0.0.1:15672"
        meilisearch_url = "http://127.0.0.1:7700"
        minio_url = "http://127.0.0.1:9000"
        flower_url = "http://127.0.0.1:5555"
        mailpit_url = "http://127.0.0.1:8025"
        nginx_url = "http://127.0.0.1"
        minio_marker = None

    return [
        Check("PostgreSQL (UTC/UTF8)", lambda: verify_postgres(postgres_host)),
        Check("Redis (authenticated)", lambda: verify_redis(redis_host)),
        Check("RabbitMQ", lambda: verify_rabbitmq(rabbitmq_url)),
        Check("Meilisearch", lambda: verify_meilisearch(meilisearch_url)),
        Check("MinIO and media bucket", lambda: verify_minio(minio_url, minio_marker)),
        Check(
            "Backend health",
            lambda: fetch(
                f"{backend_url}/health/ready",
                expected_text='"status":"ready"',
            ),
        ),
        Check(
            "Backend liveness",
            lambda: fetch(
                f"{backend_url}/health/live",
                expected_text='"status":"alive"',
            ),
        ),
        Check(
            "Backend metrics",
            lambda: fetch(
                f"{backend_url}/metrics",
                expected_text="fashion_network_http_requests_total",
            ),
        ),
        Check(
            "Backend Swagger",
            lambda: fetch(f"{backend_url}/docs", expected_text="Swagger UI"),
        ),
        Check(
            "Frontend",
            lambda: fetch(frontend_url, expected_text="Fashion Network"),
        ),
        Check(
            "Dashboard",
            lambda: fetch(dashboard_url, expected_text="Fashion Network Dashboard"),
        ),
        Check("Celery worker and Flower", lambda: verify_flower(flower_url)),
        Check("Mailpit", lambda: fetch(f"{mailpit_url}/livez")),
        Check("Nginx health", lambda: fetch(f"{nginx_url}/healthz")),
        Check(
            "Nginx frontend route",
            lambda: fetch(
                nginx_url,
                expected_text="Fashion Network",
                headers={"Host": "localhost"},
            ),
        ),
        Check(
            "Nginx dashboard route",
            lambda: fetch(
                nginx_url,
                expected_text="Fashion Network Dashboard",
                headers={"Host": "dashboard.localhost"},
            ),
        ),
        Check(
            "Nginx backend route",
            lambda: fetch(
                f"{nginx_url}/health/ready",
                expected_text='"status":"ready"',
                headers={"Host": "api.localhost"},
            ),
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify every Phase 1.5 local development service."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.development"),
        help="Environment file to load (default: .env.development).",
    )
    parser.add_argument(
        "--inside-compose",
        action="store_true",
        help="Use Compose service names instead of published localhost ports.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Overall retry timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_environment(args.env_file)
    pending = {check.name: check for check in build_checks(args.inside_compose)}
    failures: dict[str, str] = {}
    deadline = time.monotonic() + args.timeout

    while pending and time.monotonic() < deadline:
        for name, check in list(pending.items()):
            try:
                check.run()
            except Exception as error:
                failures[name] = str(error)
            else:
                print(f"[PASS] {name}", flush=True)
                pending.pop(name)
                failures.pop(name, None)
        if pending:
            time.sleep(3)

    if pending:
        print("\nEnvironment verification failed:", flush=True)
        for name in pending:
            print(f"[FAIL] {name}: {failures.get(name, 'timed out')}", flush=True)
        return 1

    print("\nAll Phase 1.5 services are healthy.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
