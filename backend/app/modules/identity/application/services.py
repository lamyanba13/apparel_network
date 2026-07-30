from typing import Protocol


class IdentityService(Protocol):
    """Reserved identity application-service boundary for a later phase."""


class SessionService(Protocol):
    """Reserved opaque-session application-service boundary for a later phase."""


class CredentialRecoveryService(Protocol):
    """Reserved recovery application-service boundary for a later phase."""
