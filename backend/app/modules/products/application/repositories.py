from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.products.domain import Product, ProductStatus, ProductVisibility


class ProductRepository(Protocol):
    async def catalog_store(self, catalog_id: UUID, owner_id: UUID) -> UUID | None: ...
    async def add(self, values: Mapping[str, object]) -> Product: ...
    async def list_for_owner(
        self,
        owner_id: UUID,
        *,
        catalog_id: UUID | None,
        status: ProductStatus | None,
        visibility: ProductVisibility | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Product], int]: ...
    async def get_for_owner(
        self, product_id: UUID, owner_id: UUID
    ) -> Product | None: ...
    async def slug_exists(
        self, catalog_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool: ...
    async def sku_exists(
        self, store_id: UUID, sku: str, *, exclude_id: UUID | None = None
    ) -> bool: ...
    async def update(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Product | None: ...
    async def archive(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> Product | None: ...

    async def transition(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        status: ProductStatus,
        expected_version: int,
    ) -> Product | None: ...
