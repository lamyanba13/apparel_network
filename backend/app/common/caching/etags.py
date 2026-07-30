import hashlib


def generate_etag(content: bytes | str) -> str:
    """Generate a strong opaque ETag from an approved representation."""
    encoded = content.encode() if isinstance(content, str) else content
    return f'"{hashlib.sha256(encoded).hexdigest()}"'


def if_none_match_matches(value: str, etag: str) -> bool:
    """Apply weak comparison for GET/HEAD `If-None-Match` evaluation."""

    def normalize(candidate: str) -> str:
        return candidate.strip().removeprefix("W/")

    normalized_etag = normalize(etag)
    return any(
        candidate.strip() == "*" or normalize(candidate) == normalized_etag
        for candidate in value.split(",")
    )
