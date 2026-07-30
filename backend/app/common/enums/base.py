from enum import StrEnum


class SortDirection(StrEnum):
    """Direction accepted by shared sort parsing."""

    ASCENDING = "asc"
    DESCENDING = "desc"


class Environment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Status(StrEnum):
    """Generic lifecycle status for infrastructure-only contracts."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class UserRole(StrEnum):
    """Placeholder values; authorization is intentionally not implemented."""

    CUSTOMER = "customer"
    STORE_OWNER = "store_owner"
    STORE_STAFF = "store_staff"
    ADMINISTRATOR = "administrator"


class ReservationStatus(StrEnum):
    """Placeholder only; Reservations owns its future state machine."""

    PENDING = "pending"
    ACTIVE = "active"
    TERMINAL = "terminal"


class InventoryStatus(StrEnum):
    """Placeholder only; Inventory owns its future availability policy."""

    AVAILABLE = "available"
    LOW_AVAILABILITY = "low_availability"
    UNAVAILABLE = "unavailable"
