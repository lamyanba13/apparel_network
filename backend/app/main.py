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
    public_rate_limit_scope,
)
from app.common.rate_limiting import RateLimiter
from app.core.config import Settings, get_settings
from app.database.lifespan import create_database_lifespan


def create_application(
    application_settings: Settings | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    rate_limit_scope_resolver: RateLimitScopeResolver = public_rate_limit_scope,
) -> FastAPI:
    """Create the FastAPI application and compose shared infrastructure."""
    resolved_settings = application_settings or get_settings()
    configure_logging(resolved_settings)
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
        lifespan=create_database_lifespan(resolved_settings),
    )
    application.state.settings = resolved_settings
    application.include_router(api_router)
    register_exception_handlers(application)

    application.add_middleware(RequestTimingMiddleware)
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
        limiter=rate_limiter,
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
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestContextMiddleware)

    install_custom_openapi(application, resolved_settings)
    return application


app = create_application()
