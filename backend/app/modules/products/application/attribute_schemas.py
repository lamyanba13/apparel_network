from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.products.domain import AttributeStatus, AttributeType


@dataclass(frozen=True, slots=True)
class AttributeCreate:
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
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class AttributeUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class AttributeValueCreate:
    value: str
    slug: str
    sort_order: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class AttributeValueUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class AttributeAssignment:
    attribute_value_id: UUID
    expected_version: int
    actor_id: UUID
