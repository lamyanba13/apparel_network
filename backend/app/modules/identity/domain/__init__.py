"""Framework-independent identity persistence invariants."""

from app.modules.identity.domain.events import (
    AuthenticationFailed,
    AuthenticationSucceeded,
    LogoutCompleted,
    RefreshReuseDetected,
    RefreshRotated,
)
from app.modules.identity.domain.values import (
    is_argon2id_hash,
    is_sha256_hex_digest,
    normalize_email,
)

__all__ = [
    "AuthenticationFailed",
    "AuthenticationSucceeded",
    "LogoutCompleted",
    "RefreshReuseDetected",
    "RefreshRotated",
    "is_argon2id_hash",
    "is_sha256_hex_digest",
    "normalize_email",
]
