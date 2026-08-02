from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProductVariant:
    id: UUID
    product_id: UUID
    store_id: UUID
    reference: str
    attributes: dict[str, str]
    attribute_signature: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
