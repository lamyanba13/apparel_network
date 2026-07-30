from enum import StrEnum


class ErrorCode(StrEnum):
    """Business-neutral machine-readable error codes."""

    DATABASE_ERROR = "database_error"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    HTTP_ERROR = "http_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
