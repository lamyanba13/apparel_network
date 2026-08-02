from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProductVariantCreate:
    reference: str
    attributes: Mapping[str, str]
    sort_order: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProductVariantUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID
