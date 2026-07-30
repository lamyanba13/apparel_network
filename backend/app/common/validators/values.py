import re
from pathlib import PurePath
from uuid import UUID

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

_EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{5,24}$")
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def validate_uuid(value: str) -> UUID:
    """Parse a UUID without relying on identifier secrecy."""
    return UUID(value)


def validate_email(value: str) -> str:
    """Validate and normalize a conservative international email shape."""
    normalized = value.strip()
    if len(normalized) > 254 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address")
    return normalized


def validate_phone(value: str) -> str:
    """Validate a regional-friendly phone representation without formatting it."""
    normalized = value.strip()
    if not _PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid phone number")
    digit_count = sum(character.isdigit() for character in normalized)
    if not 7 <= digit_count <= 15:
        raise ValueError("Invalid phone number")
    return normalized


def validate_slug(value: str) -> str:
    """Validate a lowercase kebab-case slug."""
    normalized = value.strip()
    if len(normalized) > 100 or not _SLUG_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid slug")
    return normalized


def validate_url(value: str) -> str:
    """Validate an HTTP(S) URL and return its normalized representation."""
    try:
        return str(_URL_ADAPTER.validate_python(value))
    except ValidationError as error:
        raise ValueError("Invalid HTTP URL") from error


def validate_filename(value: str) -> str:
    """Reject traversal, control characters, and unsafe filename shapes."""
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 255
        or PurePath(normalized).name != normalized
        or any(ord(character) < 32 for character in normalized)
        or normalized in {".", ".."}
    ):
        raise ValueError("Invalid filename")
    return normalized
