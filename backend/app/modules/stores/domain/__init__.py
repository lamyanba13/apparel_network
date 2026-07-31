"""Framework-independent Store domain contracts."""

from app.modules.stores.domain.events import (
    StoreClosed,
    StoreCreated,
    StoreSubmitted,
    StoreSuspended,
    StoreUpdated,
    StoreVerified,
)
from app.modules.stores.domain.models import (
    Store,
    StoreAddress,
    StoreContact,
    StoreStatus,
    VerificationStatus,
)
from app.modules.stores.domain.verification import (
    StoreVerification,
    StoreVerificationMetadata,
    StoreVerificationStatus,
)
from app.modules.stores.domain.verification_events import (
    StoreVerificationRejected,
    StoreVerificationReopened,
    StoreVerificationStarted,
    StoreVerificationSubmitted,
)

__all__ = [
    "Store",
    "StoreAddress",
    "StoreClosed",
    "StoreContact",
    "StoreCreated",
    "StoreStatus",
    "StoreSubmitted",
    "StoreSuspended",
    "StoreUpdated",
    "StoreVerification",
    "StoreVerificationMetadata",
    "StoreVerificationRejected",
    "StoreVerificationReopened",
    "StoreVerificationStarted",
    "StoreVerificationStatus",
    "StoreVerificationSubmitted",
    "StoreVerified",
    "VerificationStatus",
]
