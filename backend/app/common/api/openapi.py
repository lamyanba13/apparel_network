from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.common.config import Settings
from app.common.constants import REQUEST_ID_HEADER

_HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}


def install_custom_openapi(application: FastAPI, settings: Settings) -> None:
    """Install deterministic OpenAPI metadata and request-ID documentation."""

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema

        schema = get_openapi(
            title=settings.application_name,
            version=settings.application_version,
            description=settings.application_description,
            routes=application.routes,
        )
        schema["info"]["contact"] = {
            "name": settings.application_contact_name,
            "url": settings.application_contact_url,
        }
        schema["info"]["license"] = {
            "name": settings.application_license_name,
            "url": settings.application_license_url,
        }
        schema["servers"] = [{"url": url} for url in settings.api_server_urls]

        request_id_parameter = {
            "name": REQUEST_ID_HEADER,
            "in": "header",
            "required": False,
            "description": (
                "Optional client request identifier. A new UUIDv7 is generated "
                "when the supplied value is absent or invalid."
            ),
            "schema": {"type": "string", "format": "uuid"},
        }
        for path_item in schema.get("paths", {}).values():
            for method, operation in path_item.items():
                if method in _HTTP_METHODS:
                    operation.setdefault("parameters", []).append(
                        request_id_parameter.copy()
                    )

        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]
