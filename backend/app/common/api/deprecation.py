from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime

from starlette.responses import Response

from app.common.constants import DEPRECATION_HEADER, SUNSET_HEADER
from app.common.utils import ensure_utc


@dataclass(frozen=True, slots=True)
class DeprecationPolicy:
    """Headers for an explicitly reviewed endpoint deprecation."""

    deprecated_at: datetime
    sunset_at: datetime | None = None
    documentation_url: str | None = None

    def __post_init__(self) -> None:
        deprecated_at = ensure_utc(self.deprecated_at)
        object.__setattr__(self, "deprecated_at", deprecated_at)
        if self.sunset_at is not None:
            sunset_at = ensure_utc(self.sunset_at)
            if sunset_at <= deprecated_at:
                raise ValueError("sunset_at must be later than deprecated_at")
            object.__setattr__(self, "sunset_at", sunset_at)


def apply_deprecation_headers(
    response: Response,
    policy: DeprecationPolicy,
) -> None:
    """Apply standardized deprecation metadata to one reviewed response."""
    response.headers[DEPRECATION_HEADER] = f"@{int(policy.deprecated_at.timestamp())}"
    if policy.sunset_at is not None:
        response.headers[SUNSET_HEADER] = format_datetime(
            policy.sunset_at,
            usegmt=True,
        )
    if policy.documentation_url is not None:
        response.headers.append(
            "Link",
            f'<{policy.documentation_url}>; rel="deprecation"',
        )
