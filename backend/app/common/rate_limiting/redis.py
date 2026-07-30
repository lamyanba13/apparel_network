from __future__ import annotations

import hashlib
from collections.abc import Mapping

from redis.asyncio import Redis

from app.common.rate_limiting.contracts import (
    RateLimitDecision,
    RateLimiter,
    RateLimitPolicy,
    RateLimitScope,
)

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RedisRateLimiter(RateLimiter):
    """Atomic fixed-window limiter for ephemeral abuse controls."""

    def __init__(
        self,
        redis_url: str,
        policies: Mapping[RateLimitScope, RateLimitPolicy],
    ) -> None:
        self._redis = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        self._policies = dict(policies)

    async def check(
        self,
        *,
        scope: RateLimitScope,
        key: str,
    ) -> RateLimitDecision:
        policy = self._policies[scope]
        safe_key = hashlib.sha256(key.encode()).hexdigest()
        redis_key = f"rate-limit:{scope.value}:{safe_key}"
        result = await self._redis.eval(
            _FIXED_WINDOW_SCRIPT,
            1,
            redis_key,
            policy.window_seconds,
        )
        current, ttl = (int(value) for value in result)
        remaining = max(policy.limit - current, 0)
        return RateLimitDecision(
            is_allowed=current <= policy.limit,
            limit=policy.limit,
            remaining=remaining,
            retry_after_seconds=max(ttl, 1) if current > policy.limit else None,
        )

    async def close(self) -> None:
        await self._redis.aclose()
