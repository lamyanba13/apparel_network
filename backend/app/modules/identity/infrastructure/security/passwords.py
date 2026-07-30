from pwdlib import PasswordHash
from pydantic import SecretStr


class PwdlibPasswordService:
    """Argon2id-only password operations backed by pwdlib."""

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()
        self._dummy_hash = self._hasher.hash("fashion-network-dummy-password")

    def hash_password(self, password: SecretStr) -> str:
        return self._hasher.hash(password.get_secret_value())

    def verify_password(self, password: SecretStr, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password.get_secret_value(), password_hash)
        except (ValueError, TypeError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return bool(self._hasher.current_hasher.check_needs_rehash(password_hash))
        except (ValueError, TypeError):
            return True

    def verify_dummy(self, password: SecretStr) -> None:
        self._hasher.verify(password.get_secret_value(), self._dummy_hash)
