from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from starlette.types import Scope

from app.common.rate_limiting import (
    RateLimitDecision,
    RateLimitScope,
)
from app.core.config import Settings
from app.main import create_application


@dataclass
class FakeRateLimiter:
    decision: RateLimitDecision
    calls: list[tuple[RateLimitScope, str]] = field(default_factory=list)

    async def check(
        self,
        *,
        scope: RateLimitScope,
        key: str,
    ) -> RateLimitDecision:
        self.calls.append((scope, key))
        return self.decision


def admin_scope(_: Scope) -> RateLimitScope:
    return RateLimitScope.ADMIN


def test_rate_limiting_is_disabled_by_default(test_settings: Settings) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "ratelimit-limit" not in response.headers


def test_enabled_rate_limiting_requires_an_adapter(test_settings: Settings) -> None:
    enabled_settings = test_settings.model_copy(update={"rate_limit_enabled": True})
    application = create_application(enabled_settings)

    with (
        pytest.raises(
            RuntimeError,
            match="without a RateLimiter",
        ),
        TestClient(application),
    ):
        pass


def test_rate_limiter_can_apply_a_future_route_scope(
    test_settings: Settings,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitDecision(
            is_allowed=True,
            limit=50,
            remaining=49,
        )
    )
    enabled_settings = test_settings.model_copy(update={"rate_limit_enabled": True})
    application = create_application(
        enabled_settings,
        rate_limiter=limiter,
        rate_limit_scope_resolver=admin_scope,
    )

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "50"
    assert response.headers["RateLimit-Remaining"] == "49"
    assert limiter.calls == [(RateLimitScope.ADMIN, "testclient")]


def test_rate_limiter_returns_standard_429_problem(
    test_settings: Settings,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitDecision(
            is_allowed=False,
            limit=10,
            remaining=0,
            retry_after_seconds=30,
        )
    )
    enabled_settings = test_settings.model_copy(update={"rate_limit_enabled": True})

    with TestClient(
        create_application(enabled_settings, rate_limiter=limiter)
    ) as client:
        response = client.get("/health")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["code"] == "rate_limit_exceeded"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
