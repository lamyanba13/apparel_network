from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RateLimitScope(StrEnum):
    """Coarse transport scopes; feature policy remains future work."""

    PUBLIC = "public"
    STORE = "store"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Provider-neutral result returned by a future Redis adapter."""

    is_allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit must be positive")
        if not 0 <= self.remaining <= self.limit:
            raise ValueError("remaining must be between zero and limit")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative")


class RateLimiter(Protocol):
    """Port implemented by the future ephemeral Redis rate limiter."""

    async def check(
        self,
        *,
        scope: RateLimitScope,
        key: str,
    ) -> RateLimitDecision: ...
