from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.common.exceptions import AppError
from app.modules.products.application.variant_schemas import (
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.application.variant_services import (
    ProductVariantService,
    ProductVariantValidationService,
)
from app.modules.products.domain.variants import ProductVariant

STORE = UUID(int=1)
PRODUCT = UUID(int=2)
OWNER = UUID(int=3)
NOW = datetime.now(UTC)


def variant(version: int = 1) -> ProductVariant:
    return ProductVariant(
        UUID(int=4),
        PRODUCT,
        STORE,
        "LINEN-NAVY-M",
        {"color": "Navy", "size": "M"},
        ProductVariantValidationService.signature({"color": "Navy", "size": "M"}),
        0,
        True,
        NOW,
        NOW,
        None,
        version,
        OWNER,
        OWNER,
    )


class Repository:
    async def product_store(self, product_id: UUID, owner_id: UUID) -> UUID | None:
        return STORE if product_id == PRODUCT and owner_id == OWNER else None

    async def add(self, values: Mapping[str, object]) -> ProductVariant:
        return variant()

    async def list_for_product(
        self, product_id: UUID, owner_id: UUID
    ) -> list[ProductVariant]:
        return [variant()]

    async def get_for_owner(
        self, variant_id: UUID, product_id: UUID, owner_id: UUID
    ) -> ProductVariant | None:
        return (
            variant()
            if variant_id == UUID(int=4) and product_id == PRODUCT and owner_id == OWNER
            else None
        )

    async def reference_exists(
        self, store_id: UUID, reference: str, *, exclude_id: UUID | None = None
    ) -> bool:
        return reference == "DUPLICATE"

    async def signature_exists(
        self, product_id: UUID, signature: str, *, exclude_id: UUID | None = None
    ) -> bool:
        return False

    async def update(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductVariant | None:
        return variant() if expected_version == 1 else None

    async def archive(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> ProductVariant | None:
        return variant() if expected_version == 1 else None


def test_attributes_are_canonical_and_signature_is_stable() -> None:
    validation = ProductVariantValidationService()
    first = validation.attributes({" Size ": " M ", "Color": "Navy"})
    second = validation.attributes({"color": "Navy", "size": "M"})
    assert first == second == {"color": "Navy", "size": "M"}
    assert validation.signature(first) == validation.signature(second)


def test_variant_validation_rejects_empty_attributes() -> None:
    with pytest.raises(AppError):
        ProductVariantValidationService().create(
            ProductVariantCreate("REF-1", {}, 0, OWNER)
        )


@pytest.mark.asyncio
async def test_create_normalizes_reference_and_checks_ownership() -> None:
    result = await ProductVariantService(Repository()).create(
        PRODUCT, ProductVariantCreate("linen-navy-m", {"size": "M"}, 0, OWNER)
    )
    assert result.id == UUID(int=4)
    with pytest.raises(AppError):
        await ProductVariantService(Repository()).create(
            PRODUCT, ProductVariantCreate("REF-1", {"size": "M"}, 0, UUID(int=9))
        )


@pytest.mark.asyncio
async def test_update_and_delete_honor_optimistic_version() -> None:
    service = ProductVariantService(Repository())
    await service.update_owned(
        UUID(int=4),
        PRODUCT,
        OWNER,
        ProductVariantUpdate({"is_active": False}, 1, OWNER),
    )
    await service.delete_owned(UUID(int=4), PRODUCT, OWNER, 1)
    with pytest.raises(AppError):
        await service.update_owned(
            UUID(int=4),
            PRODUCT,
            OWNER,
            ProductVariantUpdate({"is_active": True}, 2, OWNER),
        )
