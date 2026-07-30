import hashlib
import secrets

from pydantic import SecretStr


class OpaqueAccountTokenService:
    """Generate 256-bit opaque account tokens and deterministic hashes."""

    @staticmethod
    def generate() -> SecretStr:
        return SecretStr(secrets.token_urlsafe(32))

    @staticmethod
    def hash(token: SecretStr | str) -> str:
        value = token.get_secret_value() if isinstance(token, SecretStr) else token
        return hashlib.sha256(value.encode()).hexdigest()
