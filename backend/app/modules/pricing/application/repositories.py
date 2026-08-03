from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.pricing.application.schemas import ProductPriceFilter
from app.modules.pricing.domain import PriceStatus, ProductPrice


class ProductPriceRepository(Protocol):
    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool: ...

    async def product_context(
        self, product_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None: ...

    async def catalog_owned(
        self, catalog_id: UUID, store_id: UUID, owner_id: UUID
    ) -> bool: ...

    async def variant_owned(
        self, variant_id: UUID, product_id: UUID, store_id: UUID, owner_id: UUID
    ) -> bool: ...

    async def active_price_exists(
        self,
        *,
        product_id: UUID,
        variant_id: UUID | None,
        currency_code: str,
        effective_from: datetime | None,
        effective_until: datetime | None,
        exclude_id: UUID | None = None,
    ) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> ProductPrice: ...

    async def list_for_owner(
        self, owner_id: UUID, filters: ProductPriceFilter
    ) -> tuple[Sequence[ProductPrice], int]: ...

    async def get_for_owner(
        self, price_id: UUID, owner_id: UUID
    ) -> ProductPrice | None: ...

    async def update(
        self,
        price_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductPrice | None: ...

    async def archive(
        self,
        price_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ProductPrice | None: ...

    async def transition(
        self,
        price_id: UUID,
        owner_id: UUID,
        *,
        status: PriceStatus,
        expected_version: int,
        updated_by_id: UUID,
    ) -> ProductPrice | None: ...
