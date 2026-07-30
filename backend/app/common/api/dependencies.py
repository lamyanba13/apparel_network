from collections.abc import Collection, Mapping, Sequence
from typing import Annotated

from fastapi import Header, Query, Request

from app.common.constants import IDEMPOTENCY_KEY_HEADER
from app.common.context import RequestContext, get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.common.idempotency import IdempotencyKey, parse_idempotency_key
from app.common.pagination import (
    CursorPagination,
    FilterParameters,
    OffsetPagination,
    SortParameter,
    parse_sort,
)
from app.common.types import AuthenticatedUser


def offset_pagination_dependency(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OffsetPagination:
    """Build validated offset pagination from query parameters."""
    return OffsetPagination(offset=offset, limit=limit)


def cursor_pagination_dependency(
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CursorPagination:
    """Build validated cursor pagination from query parameters."""
    return CursorPagination(cursor=cursor, limit=limit)


def request_context_dependency() -> RequestContext:
    """Expose the current request context through dependency injection."""
    return get_request_context()


def current_user_dependency() -> AuthenticatedUser | None:
    """Return the placeholder actor until Auth supplies one in a later phase."""
    return get_request_context().authenticated_user


def idempotency_key_dependency(
    value: Annotated[str, Header(alias=IDEMPOTENCY_KEY_HEADER)],
) -> IdempotencyKey:
    """Validate a required idempotency key for an opted-in command."""
    try:
        return parse_idempotency_key(value)
    except ValueError as error:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            title="Request validation failed",
            detail="The idempotency key is invalid.",
            status_code=422,
            errors=[
                FieldError(
                    field="header.idempotency-key",
                    code="invalid_idempotency_key",
                    message=str(error),
                )
            ],
        ) from error


def sorting_dependency(
    value: str,
    *,
    allowed_fields: Collection[str],
) -> SortParameter:
    """Parse one caller-supplied sort expression against endpoint policy."""
    return parse_sort(value, allowed_fields=allowed_fields)


def filtering_dependency(
    request: Request,
    *,
    allowed_fields: Collection[str],
) -> FilterParameters:
    """Collect repeated allowlisted filters without interpreting business meaning."""
    values: dict[str, list[str]] = {}
    for field in allowed_fields:
        field_values = request.query_params.getlist(field)
        if field_values:
            values[field] = field_values
    return FilterParameters.from_mapping(values)


def normalize_filter_mapping(
    values: Mapping[str, Sequence[str]],
) -> FilterParameters:
    """Normalize filters supplied outside an HTTP dependency."""
    return FilterParameters.from_mapping(values)
