from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.common.api import install_custom_openapi, register_exception_handlers
from app.common.enums import Environment
from app.common.logging import configure_logging
from app.common.middleware import (
    AdaptiveCompressionMiddleware,
    ETagMiddleware,
    RateLimitMiddleware,
    RateLimitScopeResolver,
    RequestContextMiddleware,
    RequestLoggingMiddleware,
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
    authentication_rate_limit_scope,
)
from app.common.rate_limiting import RateLimiter, RateLimitPolicy, RateLimitScope
from app.common.rate_limiting.redis import RedisRateLimiter
from app.core.config import Settings, get_settings
from app.database.lifespan import Lifespan, create_database_lifespan
from app.modules.identity.application.authorization import PermissionCache
from app.modules.identity.infrastructure.activity import SessionActivityMiddleware
from app.modules.identity.infrastructure.authorization_cache import (
    RedisPermissionCache,
)
from app.modules.identity.infrastructure.events import AuthenticationEventPublisher
from app.modules.identity.infrastructure.security import (
    JwtTokenService,
    PwdlibPasswordService,
)
from app.observability import (
    MetricsMiddleware,
    configure_fastapi_telemetry,
    configure_sentry,
    metrics_response,
)


def create_application(
    application_settings: Settings | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    permission_cache: PermissionCache | None = None,
    rate_limit_scope_resolver: RateLimitScopeResolver = (
        authentication_rate_limit_scope
    ),
) -> FastAPI:
    """Create the FastAPI application and compose shared infrastructure."""
    resolved_settings = application_settings or get_settings()
    resolved_permission_cache = permission_cache or RedisPermissionCache(
        resolved_settings.redis_url,
        ttl_seconds=resolved_settings.authorization_cache_ttl_seconds,
    )
    resolved_rate_limiter = rate_limiter
    if resolved_settings.rate_limit_enabled and resolved_rate_limiter is None:
        window = resolved_settings.auth_rate_limit_window_seconds
        resolved_rate_limiter = RedisRateLimiter(
            resolved_settings.redis_url,
            {
                RateLimitScope.PUBLIC: RateLimitPolicy(
                    resolved_settings.public_rate_limit,
                    window,
                ),
                RateLimitScope.STORE: RateLimitPolicy(
                    resolved_settings.store_rate_limit,
                    window,
                ),
                RateLimitScope.ADMIN: RateLimitPolicy(
                    resolved_settings.admin_rate_limit,
                    window,
                ),
                RateLimitScope.AUTH_LOGIN: RateLimitPolicy(
                    resolved_settings.auth_login_rate_limit,
                    window,
                ),
                RateLimitScope.AUTH_REFRESH: RateLimitPolicy(
                    resolved_settings.auth_refresh_rate_limit,
                    window,
                ),
                RateLimitScope.PASSWORD_RESET: RateLimitPolicy(
                    resolved_settings.auth_login_rate_limit,
                    window,
                ),
            },
        )
    configure_logging(resolved_settings)
    configure_sentry(resolved_settings)
    expose_development_docs = resolved_settings.environment in {
        Environment.DEVELOPMENT,
        Environment.TEST,
    }
    application = FastAPI(
        title=resolved_settings.application_name,
        version=resolved_settings.application_version,
        description=resolved_settings.application_description,
        contact={
            "name": resolved_settings.application_contact_name,
            "url": resolved_settings.application_contact_url,
        },
        license_info={
            "name": resolved_settings.application_license_name,
            "url": resolved_settings.application_license_url,
        },
        docs_url="/docs" if expose_development_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_development_docs else None,
        lifespan=_application_lifespan(
            resolved_settings,
            resolved_permission_cache,
            resolved_rate_limiter,
        ),
    )
    application.state.settings = resolved_settings
    application.state.password_service = PwdlibPasswordService()
    application.state.authentication_events = AuthenticationEventPublisher()
    application.state.account_notifications = None
    application.state.token_service = (
        JwtTokenService(resolved_settings)
        if resolved_settings.jwt_private_key_pem is not None
        else None
    )
    application.state.rate_limiter = resolved_rate_limiter
    application.state.permission_cache = resolved_permission_cache
    application.include_router(api_router)
    if resolved_settings.metrics_enabled:
        application.add_api_route(
            resolved_settings.metrics_path,
            metrics_response,
            methods=["GET"],
            include_in_schema=False,
        )
    register_exception_handlers(application)

    application.add_middleware(RequestTimingMiddleware)
    application.add_middleware(
        SessionActivityMiddleware,
        throttle_seconds=resolved_settings.session_activity_throttle_seconds,
    )
    application.add_middleware(
        MetricsMiddleware,
        enabled=resolved_settings.metrics_enabled,
    )
    application.add_middleware(
        AdaptiveCompressionMiddleware,
        minimum_size=resolved_settings.gzip_minimum_size,
        brotli_enabled=resolved_settings.brotli_enabled,
        brotli_quality=resolved_settings.brotli_quality,
    )
    application.add_middleware(
        ETagMiddleware,
        enabled=resolved_settings.etag_enabled,
    )
    application.add_middleware(
        RateLimitMiddleware,
        enabled=resolved_settings.rate_limit_enabled,
        limiter=resolved_rate_limiter,
        scope_resolver=rate_limit_scope_resolver,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.trusted_hosts,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=resolved_settings.cors_allow_credentials,
        allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-Correlation-ID",
            "X-Request-ID",
        ],
        expose_headers=[
            "X-Correlation-ID",
            "X-Process-Time-Ms",
            "X-Request-ID",
        ],
    )
    application.add_middleware(
        SecurityHeadersMiddleware,
        environment=resolved_settings.environment,
    )
    application.add_middleware(
        RequestLoggingMiddleware,
        slow_request_threshold_ms=resolved_settings.slow_request_threshold_ms,
    )
    application.add_middleware(RequestContextMiddleware)

    install_custom_openapi(application, resolved_settings)
    configure_fastapi_telemetry(application, resolved_settings)
    return application


def _application_lifespan(
    application_settings: Settings,
    permission_cache: PermissionCache,
    rate_limiter: RateLimiter | None,
) -> Lifespan:
    database_lifespan = create_database_lifespan(application_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            async with database_lifespan(application):
                yield
        finally:
            await permission_cache.close()
            if rate_limiter is not None:
                await rate_limiter.close()

    return lifespan


app = create_application()
