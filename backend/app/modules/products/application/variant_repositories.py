from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.products.domain.variants import ProductVariant


class ProductVariantRepository(Protocol):
    async def product_store(self, product_id: UUID, owner_id: UUID) -> UUID | None: ...
    async def add(self, values: Mapping[str, object]) -> ProductVariant: ...
    async def list_for_product(
        self, product_id: UUID, owner_id: UUID
    ) -> Sequence[ProductVariant]: ...
    async def get_for_owner(
        self, variant_id: UUID, product_id: UUID, owner_id: UUID
    ) -> ProductVariant | None: ...
    async def reference_exists(
        self, store_id: UUID, reference: str, *, exclude_id: UUID | None = None
    ) -> bool: ...
    async def signature_exists(
        self, product_id: UUID, signature: str, *, exclude_id: UUID | None = None
    ) -> bool: ...
    async def update(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductVariant | None: ...
    async def archive(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> ProductVariant | None: ...
