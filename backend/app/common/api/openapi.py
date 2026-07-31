from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.common.config import Settings
from app.common.constants import REQUEST_ID_HEADER
from app.common.errors import ProblemDetails

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
        schema["tags"] = [
            {
                "name": "Authentication",
                "description": (
                    "Identity authentication and token lifecycle operations."
                ),
            },
            {
                "name": "Sessions",
                "description": "Authenticated device-session lifecycle operations.",
            },
            {
                "name": "Account Security",
                "description": "Password and email-verification security operations.",
            },
        ]
        _install_problem_details_schema(schema)

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
                    _normalize_error_responses(operation)

        for route in application.routes:
            if not isinstance(route, APIRoute):
                continue
            requirements = _authorization_requirements(route.dependant)
            if not requirements:
                continue
            path_item = schema.get("paths", {}).get(route.path, {})
            for method in route.methods or set():
                operation = path_item.get(method.lower())
                if operation is not None:
                    operation["x-authorization"] = requirements

        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]


def _install_problem_details_schema(schema: dict[str, Any]) -> None:
    generated = ProblemDetails.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    definitions = generated.pop("$defs", {})
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.update(definitions)
    components["ProblemDetails"] = generated


def _normalize_error_responses(operation: dict[str, Any]) -> None:
    for status_code, response in operation.get("responses", {}).items():
        try:
            is_error = int(status_code) >= 400
        except ValueError:
            is_error = False
        if not is_error:
            continue
        content = response.setdefault("content", {})
        problem = content.pop("application/problem+json", {})
        content.pop("application/json", None)
        problem["schema"] = {
            "$ref": "#/components/schemas/ProblemDetails",
        }
        example = problem.get("example")
        if isinstance(example, dict):
            example.setdefault("type", "https://docs.example.invalid/problems/error")
            example.setdefault("instance", "/api/v1/example")
            example.setdefault("request_id", "01912345-6789-7abc-8def-0123456789ab")
            example.setdefault("errors", [])
        content["application/problem+json"] = problem


def _authorization_requirements(dependant: Any) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for dependency in dependant.dependencies:
        requirement = getattr(
            dependency.call,
            "__authorization_requirement__",
            None,
        )
        if requirement is not None:
            requirements.append(
                {
                    "kind": requirement.kind,
                    "values": list(requirement.values),
                }
            )
        requirements.extend(_authorization_requirements(dependency))
    return requirements
