from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.products.domain import (
    OutboxEvent,
    ProductAttribute,
    ProductAttributeValue,
    VariantAttributeAssignment,
    VariantAttributeValue,
)
from app.modules.products.domain.variant_events import VariantEvent


class AttributeRepository(Protocol):
    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool: ...

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> ProductAttribute: ...

    async def list_for_owner(
        self, owner_id: UUID, *, store_id: UUID | None = None
    ) -> Sequence[ProductAttribute]: ...

    async def get_for_owner(
        self, attribute_id: UUID, owner_id: UUID
    ) -> ProductAttribute | None: ...

    async def update(
        self,
        attribute_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductAttribute | None: ...

    async def archive(
        self,
        attribute_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ProductAttribute | None: ...


class AttributeValueRepository(Protocol):
    async def value_exists(
        self, attribute_id: UUID, value: str, *, exclude_id: UUID | None = None
    ) -> bool: ...

    async def slug_exists(
        self, attribute_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool: ...

    async def add(
        self, attribute_id: UUID, values: Mapping[str, object]
    ) -> ProductAttributeValue: ...

    async def get_for_owner(
        self, value_id: UUID, owner_id: UUID
    ) -> ProductAttributeValue | None: ...

    async def update(
        self,
        value_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductAttributeValue | None: ...

    async def delete(
        self, value_id: UUID, owner_id: UUID, *, expected_version: int
    ) -> bool | None: ...


class VariantAttributeRepository(Protocol):
    async def variant_context(
        self, variant_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None: ...

    async def value_context(
        self, value_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None: ...

    async def list_for_variant(
        self, variant_id: UUID, owner_id: UUID
    ) -> Sequence[VariantAttributeValue] | None: ...

    async def combination_exists(
        self, product_id: UUID, signature: str, *, exclude_id: UUID
    ) -> bool: ...

    async def assign(
        self,
        variant_id: UUID,
        value_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        signature: str,
    ) -> VariantAttributeAssignment | None: ...

    async def remove(
        self,
        variant_id: UUID,
        value_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        signature: str,
    ) -> VariantAttributeAssignment | None: ...


class OutboxRepository(Protocol):
    async def add(self, event: VariantEvent) -> OutboxEvent: ...
