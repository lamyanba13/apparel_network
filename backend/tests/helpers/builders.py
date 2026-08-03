from datetime import UTC, datetime
from uuid import UUID


def deterministic_uuid(value: int) -> UUID:
    return UUID(int=value)


def deterministic_timestamp() -> datetime:
    return datetime(2026, 8, 3, tzinfo=UTC)


def slug(value: int, prefix: str = "test") -> str:
    return f"{prefix}-{value}"


def email(value: int) -> str:
    return f"test-user-{value}@example.test"


def store_name(value: int) -> str:
    return f"Test Store {value}"


def catalog_name(value: int) -> str:
    return f"Test Catalog {value}"


def product_name(value: int) -> str:
    return f"Test Product {value}"


def variant_reference(value: int) -> str:
    return f"TEST-VARIANT-{value}"
