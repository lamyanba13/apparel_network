import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def normalize_whitespace(value: str) -> str:
    """Trim text and collapse consecutive whitespace."""
    return _WHITESPACE.sub(" ", value).strip()


def to_slug(value: str) -> str:
    """Create a deterministic ASCII slug for non-authoritative display uses."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_SLUG.sub("-", ascii_value).strip("-")
