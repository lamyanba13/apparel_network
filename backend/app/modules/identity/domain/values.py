from __future__ import annotations

import re

_SHA256_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def normalize_email(value: str) -> str:
    """Return the canonical case-insensitive identity lookup value."""
    return value.strip().lower()


def is_argon2id_hash(value: str) -> bool:
    """Return whether a value has the encoded Argon2id hash prefix."""
    return value.startswith("$argon2id$")


def is_sha256_hex_digest(value: str) -> bool:
    """Return whether a value is a lowercase SHA-256 hexadecimal digest."""
    return _SHA256_HEX_DIGEST.fullmatch(value) is not None
