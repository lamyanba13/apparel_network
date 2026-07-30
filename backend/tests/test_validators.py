from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

import pytest

from app.common.utils import ensure_utc, to_slug
from app.common.validators import (
    validate_email,
    validate_filename,
    validate_phone,
    validate_slug,
    validate_url,
    validate_uuid,
)


def test_shared_validators_accept_safe_values() -> None:
    identifier = uuid4()

    assert validate_uuid(str(identifier)) == identifier
    assert validate_email("person@example.com") == "person@example.com"
    assert validate_phone("+91 98765 43210") == "+91 98765 43210"
    assert validate_slug("summer-shirts") == "summer-shirts"
    assert validate_url("https://example.com/path") == "https://example.com/path"
    assert validate_filename("image-01.webp") == "image-01.webp"
    assert to_slug("Summer Shirts") == "summer-shirts"


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validate_email, "invalid"),
        (validate_phone, "123"),
        (validate_slug, "Invalid Slug"),
        (validate_url, "file:///etc/passwd"),
        (validate_filename, "../secret.txt"),
    ],
)
def test_shared_validators_reject_unsafe_values(
    validator: Callable[[str], object],
    value: str,
) -> None:
    with pytest.raises(ValueError):
        validator(value)


def test_timezone_helper_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2026, 1, 1))
