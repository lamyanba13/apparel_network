import hashlib
import re
from dataclasses import dataclass

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Validated opaque request key."""

    value: str


def parse_idempotency_key(value: str) -> IdempotencyKey:
    """Validate a high-entropy-compatible, log-safe key shape."""
    normalized = value.strip()
    if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized):
        raise ValueError("Idempotency key must contain 16-128 safe ASCII characters")
    return IdempotencyKey(normalized)


def build_request_fingerprint(
    *,
    method: str,
    path: str,
    canonical_body: bytes,
) -> str:
    """Hash the canonical operation input without retaining request data."""
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\0")
    digest.update(path.encode())
    digest.update(b"\0")
    digest.update(canonical_body)
    return digest.hexdigest()
