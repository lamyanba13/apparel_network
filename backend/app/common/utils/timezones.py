from datetime import UTC, datetime


def ensure_utc(value: datetime) -> datetime:
    """Convert an aware datetime to UTC and reject ambiguous naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required")
    return value.astimezone(UTC)
