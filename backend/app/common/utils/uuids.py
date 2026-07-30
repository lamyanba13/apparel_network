from uuid import UUID

from uuid6 import uuid7


def generate_uuid7() -> UUID:
    """Generate the approved time-ordered identifier."""
    return uuid7()


def parse_optional_uuid(value: str | None) -> UUID | None:
    """Return a parsed UUID or `None` for absent/invalid untrusted input."""
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
