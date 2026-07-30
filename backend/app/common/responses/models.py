from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.types import JsonObject


class ResponseError(BaseModel):
    """One error in the optional generic response envelope."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    field: str | None = None


class SuccessResponse[DataT](BaseModel):
    """Success envelope for contracts that require metadata."""

    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    data: DataT
    meta: JsonObject = Field(default_factory=dict)
    errors: None = None


class FailureResponse(BaseModel):
    """Generic failure envelope available to explicitly reviewed contracts."""

    model_config = ConfigDict(extra="forbid")

    success: Literal[False] = False
    data: None = None
    errors: list[ResponseError]


def success_response[DataT](
    data: DataT,
    *,
    meta: JsonObject | None = None,
) -> SuccessResponse[DataT]:
    """Build a typed success envelope."""
    return SuccessResponse(data=data, meta=meta or {})


def failure_response(errors: list[ResponseError]) -> FailureResponse:
    """Build a generic failure envelope."""
    return FailureResponse(errors=errors)
