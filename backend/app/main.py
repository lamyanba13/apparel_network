from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.database.lifespan import create_database_lifespan


def create_application(application_settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application and its database lifecycle."""
    resolved_settings = application_settings or get_settings()
    expose_development_docs = resolved_settings.environment in {
        "development",
        "test",
    }
    application = FastAPI(
        title=resolved_settings.application_name,
        version=resolved_settings.application_version,
        docs_url="/docs" if expose_development_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_development_docs else None,
        lifespan=create_database_lifespan(resolved_settings),
    )
    application.state.settings = resolved_settings
    application.include_router(api_router)
    return application


app = create_application()
