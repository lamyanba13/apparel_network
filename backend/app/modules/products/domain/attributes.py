from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AttributeType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    COLOR = "color"
    SIZE = "size"
    ENUM = "enum"


class AttributeStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DISPATCHED = "dispatched"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProductAttribute:
    id: UUID
    store_id: UUID
    name: str
    slug: str
    attribute_type: AttributeType
    description: str | None
    required: bool
    filterable: bool
    searchable: bool
    sort_order: int
    status: AttributeStatus
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ProductAttributeValue:
    id: UUID
    attribute_id: UUID
    value: str
    slug: str
    sort_order: int
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VariantAttributeAssignment:
    id: UUID
    variant_id: UUID
    attribute_value_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VariantAttributeValue:
    assignment_id: UUID
    attribute_id: UUID
    attribute_name: str
    attribute_slug: str
    attribute_type: AttributeType
    attribute_sort_order: int
    value_id: UUID
    value: str
    value_slug: str
    value_sort_order: int


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_name: str
    payload: dict[str, object]
    occurred_at: datetime
    published_at: datetime | None
    status: OutboxStatus
    retry_count: int
    version: int
    available_at: datetime
    attempts: int
    locked_at: datetime | None
    locked_by: str | None
    dispatched_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
