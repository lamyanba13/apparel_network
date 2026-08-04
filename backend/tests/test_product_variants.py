from uuid import UUID

import pytest

from app.common.exceptions import AppError
from app.modules.products.application.variant_schemas import ProductVariantCreate
from app.modules.products.application.variant_services import (
    ProductVariantValidationService,
)


def test_attributes_are_canonical_and_normalized_signature_is_stable() -> None:
    validation = ProductVariantValidationService()
    first = validation.attributes({" Size ": " M ", "Color": "Navy"})
    second = validation.attributes({"color": "Navy", "size": "M"})
    assert first == second == {"color": "Navy", "size": "M"}
    first_ids = [UUID(int=2), UUID(int=1)]
    second_ids = [UUID(int=1), UUID(int=2)]
    assert validation.signature(first_ids) == validation.signature(second_ids)


def test_variant_validation_rejects_empty_attributes() -> None:
    with pytest.raises(AppError):
        ProductVariantValidationService().create(
            ProductVariantCreate("REF-1", {}, 0, UUID(int=1))
        )
