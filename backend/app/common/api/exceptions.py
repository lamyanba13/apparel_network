from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.common.context import RequestContext
from app.common.errors import ErrorCode, FieldError, ProblemDetails
from app.common.exceptions import AppError, DatabaseError

logger = logging.getLogger(__name__)
PROBLEM_BASE_URL = "https://docs.example.invalid/problems"


def _request_id(request: Request) -> str:
    context = getattr(request.state, "request_context", None)
    if isinstance(context, RequestContext):
        return str(context.request_id)
    return "unavailable"


def _problem_response(problem: ProblemDetails) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def _problem(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    title: str,
    detail: str,
    errors: list[FieldError] | None = None,
) -> JSONResponse:
    return _problem_response(
        ProblemDetails(
            type=f"{PROBLEM_BASE_URL}/{code.value.replace('_', '-')}",
            title=title,
            status=status_code,
            code=code.value,
            detail=detail,
            instance=request.url.path,
            request_id=_request_id(request),
            errors=errors or [],
        )
    )


def _field_errors(errors: Sequence[Mapping[str, Any]]) -> list[FieldError]:
    result: list[FieldError] = []
    for error in errors:
        location = error.get("loc", ())
        field = ".".join(str(item) for item in location) or None
        result.append(
            FieldError(
                field=field,
                code=str(error.get("type", ErrorCode.VALIDATION_ERROR.value)),
                message=str(error.get("msg", "Invalid value")),
            )
        )
    return result


async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    """Translate an explicitly safe application failure."""
    return _problem(
        request,
        status_code=error.status_code,
        code=error.code,
        title=error.title,
        detail=error.detail,
        errors=error.errors,
    )


async def request_validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Translate invalid HTTP input without echoing request bodies."""
    return _problem(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        title="Request validation failed",
        detail="One or more request fields are invalid.",
        errors=_field_errors(error.errors()),
    )


async def validation_error_handler(
    request: Request,
    error: ValidationError,
) -> JSONResponse:
    """Translate Pydantic validation outside FastAPI request parsing."""
    return _problem(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        title="Validation failed",
        detail="One or more values are invalid.",
        errors=_field_errors(error.errors()),
    )


async def http_exception_handler(
    request: Request,
    error: HTTPException,
) -> JSONResponse:
    """Translate framework HTTP failures to the stable problem contract."""
    try:
        title = HTTPStatus(error.status_code).phrase
    except ValueError:
        title = "HTTP error"
    code = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
    }.get(error.status_code, ErrorCode.HTTP_ERROR)
    detail = error.detail if isinstance(error.detail, str) else title
    return _problem(
        request,
        status_code=error.status_code,
        code=code,
        title=title,
        detail=detail,
    )


async def database_error_handler(
    request: Request,
    error: SQLAlchemyError | DatabaseError,
) -> JSONResponse:
    """Log database details server-side and return a safe dependency failure."""
    logger.exception("database.request_failed", exc_info=error)
    translated = error if isinstance(error, DatabaseError) else DatabaseError()
    return await app_error_handler(request, translated)


async def unhandled_exception_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Return a production-safe response while retaining server diagnostics."""
    logger.exception("http.unhandled_exception", exc_info=error)
    return _problem(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        title="Internal server error",
        detail="The service could not complete the request.",
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Register the centralized exception translation table."""
    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(ValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    application.add_exception_handler(SQLAlchemyError, database_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_exception_handler)
