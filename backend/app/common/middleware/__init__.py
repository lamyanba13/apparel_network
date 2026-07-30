"""Cross-cutting ASGI middleware."""

from app.common.middleware.compression import AdaptiveCompressionMiddleware
from app.common.middleware.etag import ETagMiddleware
from app.common.middleware.logging import RequestLoggingMiddleware
from app.common.middleware.rate_limit import (
    RateLimitMiddleware,
    RateLimitScopeResolver,
    authentication_rate_limit_scope,
    public_rate_limit_scope,
)
from app.common.middleware.request_context import RequestContextMiddleware
from app.common.middleware.security_headers import SecurityHeadersMiddleware
from app.common.middleware.timing import RequestTimingMiddleware

__all__ = [
    "AdaptiveCompressionMiddleware",
    "ETagMiddleware",
    "RateLimitMiddleware",
    "RateLimitScopeResolver",
    "RequestContextMiddleware",
    "RequestLoggingMiddleware",
    "RequestTimingMiddleware",
    "SecurityHeadersMiddleware",
    "authentication_rate_limit_scope",
    "public_rate_limit_scope",
]
