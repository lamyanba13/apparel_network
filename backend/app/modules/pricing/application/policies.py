from __future__ import annotations

from uuid import UUID

from app.modules.pricing.application.repositories import ProductPriceRepository


class PricingOwnershipPolicy:
    def __init__(self, repository: ProductPriceRepository) -> None:
        self._repository = repository

    async def validate(
        self,
        *,
        store_id: UUID,
        product_id: UUID,
        variant_id: UUID | None,
        owner_id: UUID,
    ) -> bool:
        if not await self._repository.store_owned(store_id, owner_id):
            return False
        context = await self._repository.product_context(product_id, owner_id)
        if context is None or context.get("store_id") != store_id:
            return False
        catalog_id = context.get("catalog_id")
        if not isinstance(catalog_id, UUID) or not await self._repository.catalog_owned(
            catalog_id, store_id, owner_id
        ):
            return False
        return variant_id is None or await self._repository.variant_owned(
            variant_id, product_id, store_id, owner_id
        )
