"""Shared constants with no feature ownership."""

from app.common.constants.http import (
    CORRELATION_ID_HEADER,
    DEPRECATION_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    REQUEST_ID_HEADER,
    REQUEST_TIME_HEADER,
    SUNSET_HEADER,
)
from app.common.constants.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE_SIZE,
)

__all__ = [
    "CORRELATION_ID_HEADER",
    "DEFAULT_PAGE_SIZE",
    "DEPRECATION_HEADER",
    "IDEMPOTENCY_KEY_HEADER",
    "MAX_PAGE_SIZE",
    "MIN_PAGE_SIZE",
    "REQUEST_ID_HEADER",
    "REQUEST_TIME_HEADER",
    "SUNSET_HEADER",
]
