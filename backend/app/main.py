from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings


def create_application() -> FastAPI:
    """Create the FastAPI application without business feature wiring."""
    expose_development_docs = settings.environment in {"development", "test"}
    application = FastAPI(
        title=settings.application_name,
        version=settings.application_version,
        docs_url="/docs" if expose_development_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_development_docs else None,
    )
    application.include_router(api_router)
    return application


app = create_application()
