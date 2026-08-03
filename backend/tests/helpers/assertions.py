from httpx import Response


def assert_created(response: Response) -> None:
    assert response.status_code == 201


def assert_ok(response: Response) -> None:
    assert response.status_code == 200


def assert_bad_request(response: Response) -> None:
    assert response.status_code == 400


def assert_unauthorized(response: Response) -> None:
    assert response.status_code == 401


def assert_forbidden(response: Response) -> None:
    assert response.status_code == 403


def assert_not_found(response: Response) -> None:
    assert response.status_code == 404


def assert_conflict(response: Response) -> None:
    assert response.status_code == 409


def assert_validation_error(response: Response) -> None:
    assert response.status_code == 422
