from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    """One safe, machine-readable field failure."""

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    code: str
    message: str


class ProblemDetails(BaseModel):
    """RFC 9457-style API problem response."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int = Field(ge=400, le=599)
    code: str
    detail: str
    instance: str
    request_id: str
    errors: list[FieldError] = Field(default_factory=list)
