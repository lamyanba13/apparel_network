import pytest
from pydantic import ValidationError

from app.common.responses import (
    FailureResponse,
    ResponseError,
    SuccessResponse,
    failure_response,
    success_response,
)


def test_success_response_has_stable_envelope() -> None:
    response = success_response({"id": "example"}, meta={"source": "test"})

    assert response.model_dump() == {
        "success": True,
        "data": {"id": "example"},
        "meta": {"source": "test"},
        "errors": None,
    }
    assert isinstance(response, SuccessResponse)


def test_failure_response_has_stable_envelope() -> None:
    response = failure_response(
        [ResponseError(code="validation_error", message="Invalid value")]
    )

    assert response.model_dump() == {
        "success": False,
        "data": None,
        "errors": [
            {
                "code": "validation_error",
                "message": "Invalid value",
                "field": None,
            }
        ],
    }
    assert isinstance(response, FailureResponse)


def test_response_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SuccessResponse.model_validate({"data": {}, "unexpected": True})
