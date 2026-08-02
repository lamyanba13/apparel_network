import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.products.application.variant_repositories import (
    ProductVariantRepository,
)
from app.modules.products.application.variant_schemas import (
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.domain.variants import ProductVariant
from app.observability.metrics import (
    PRODUCT_VARIANTS_CREATED,
    PRODUCT_VARIANTS_DELETED,
    PRODUCT_VARIANTS_UPDATED,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProductVariantValidationService:
    def create(self, values: ProductVariantCreate) -> tuple[dict[str, object], str]:
        attributes = self.attributes(values.attributes)
        return {
            "reference": self.reference(values.reference),
            "attributes": attributes,
            "sort_order": self.order(values.sort_order),
            "actor_id": values.actor_id,
        }, self.signature(attributes)

    def changes(
        self, values: Mapping[str, object]
    ) -> tuple[dict[str, object], str | None]:
        allowed = {"reference", "attributes", "sort_order", "is_active"}
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        signature = None
        if "reference" in result:
            result["reference"] = self.reference(result["reference"])
        if "attributes" in result:
            attributes = self.attributes(result["attributes"])
            result["attributes"] = attributes
            signature = self.signature(attributes)
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        if "is_active" in result and not isinstance(result["is_active"], bool):
            raise _validation("is_active", "Active status must be true or false.")
        return result, signature

    @staticmethod
    def reference(value: object) -> str:
        if not isinstance(value, str) or not _REFERENCE.fullmatch(value.strip()):
            raise _validation("reference", "Reference format is invalid.")
        return value.strip().upper()

    @staticmethod
    def attributes(value: object) -> dict[str, str]:
        if not isinstance(value, Mapping) or not value or len(value) > 12:
            raise _validation(
                "attributes", "Provide between one and twelve attributes."
            )
        result: dict[str, str] = {}
        for name, attribute_value in value.items():
            if not isinstance(name, str) or not isinstance(attribute_value, str):
                raise _validation(
                    "attributes", "Attributes must contain text keys and values."
                )
            normalized_name, normalized_value = " ".join(name.split()), " ".join(
                attribute_value.split()
            )
            if (
                not 1 <= len(normalized_name) <= 50
                or not 1 <= len(normalized_value) <= 100
            ):
                raise _validation(
                    "attributes", "Attribute key or value length is invalid."
                )
            key = normalized_name.casefold()
            if key in result:
                raise _validation("attributes", "Attribute names must be unique.")
            result[key] = normalized_value
        return dict(sorted(result.items()))

    @staticmethod
    def signature(attributes: Mapping[str, str]) -> str:
        canonical = json.dumps(
            dict(attributes), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def order(value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise _validation("sort_order", "Sort order must be non-negative.")
        return value


class ProductVariantService:
    def __init__(self, repository: ProductVariantRepository) -> None:
        self._repository = repository
        self._validation = ProductVariantValidationService()

    async def create(
        self, product_id: UUID, values: ProductVariantCreate
    ) -> ProductVariant:
        store_id = await self._repository.product_store(product_id, values.actor_id)
        if store_id is None:
            raise _not_found()
        validated, signature = self._validation.create(values)
        if await self._repository.reference_exists(
            store_id, str(validated["reference"])
        ):
            raise _conflict("Variant reference already exists in this Store.")
        if await self._repository.signature_exists(product_id, signature):
            raise _conflict("A variant with these attributes already exists.")
        variant = await self._repository.add(
            {
                **validated,
                "product_id": product_id,
                "store_id": store_id,
                "attribute_signature": signature,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        PRODUCT_VARIANTS_CREATED.inc()
        return variant

    async def list_owned(
        self, product_id: UUID, owner_id: UUID
    ) -> Sequence[ProductVariant]:
        if await self._repository.product_store(product_id, owner_id) is None:
            raise _not_found()
        return await self._repository.list_for_product(product_id, owner_id)

    async def update_owned(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        values: ProductVariantUpdate,
    ) -> ProductVariant:
        existing = await self._repository.get_for_owner(
            variant_id, product_id, owner_id
        )
        if existing is None:
            raise _not_found()
        changes, signature = self._validation.changes(values.values)
        if "reference" in changes and await self._repository.reference_exists(
            existing.store_id, str(changes["reference"]), exclude_id=variant_id
        ):
            raise _conflict("Variant reference already exists in this Store.")
        if signature is not None:
            if await self._repository.signature_exists(
                product_id, signature, exclude_id=variant_id
            ):
                raise _conflict("A variant with these attributes already exists.")
            changes["attribute_signature"] = signature
        variant = await self._repository.update(
            variant_id,
            product_id,
            owner_id,
            values={**changes, "updated_by_id": owner_id},
            expected_version=values.expected_version,
        )
        if variant is None:
            raise _conflict("The variant was modified by another request.")
        PRODUCT_VARIANTS_UPDATED.inc()
        return variant

    async def delete_owned(
        self, variant_id: UUID, product_id: UUID, owner_id: UUID, version: int
    ) -> None:
        if (
            await self._repository.archive(
                variant_id,
                product_id,
                owner_id,
                expected_version=version,
                deleted_at=datetime.now(UTC),
            )
            is None
        ):
            raise _not_found()
        PRODUCT_VARIANTS_DELETED.inc()


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Product variant validation failed",
        detail="Variant fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_variant_field", message=message)],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Product variant not found",
        detail="The requested Product variant was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Product variant conflict",
        detail=detail,
        status_code=409,
    )
