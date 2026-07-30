from http import HTTPStatus

from app.common.errors import ErrorCode, FieldError


class AppError(Exception):
    """A safe application failure that can cross the HTTP boundary."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        detail: str,
        status_code: int,
        title: str | None = None,
        errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.title = title or HTTPStatus(status_code).phrase
        self.errors = errors or []


class DatabaseError(AppError):
    """Safe translation target for database infrastructure failures."""

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.DATABASE_ERROR,
            detail="The service could not complete the database operation.",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            title="Database unavailable",
        )
