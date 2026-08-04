import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.products.application.attribute_services import (
    OutboxService,
    normalized_attribute_signature,
)
from app.modules.products.application.variant_repositories import (
    ProductVariantRepository,
)
from app.modules.products.application.variant_schemas import (
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.domain import (
    VariantArchived,
    VariantCreated,
    VariantDeleted,
    VariantUpdated,
)
from app.modules.products.domain.variants import ProductVariant
from app.observability.metrics import (
    PRODUCT_VARIANTS_CREATED,
    PRODUCT_VARIANTS_DELETED,
    PRODUCT_VARIANTS_UPDATED,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProductVariantValidationService:
    def create(self, values: ProductVariantCreate) -> dict[str, object]:
        attributes = self.attributes(values.attributes)
        return {
            "reference": self.reference(values.reference),
            "attributes": attributes,
            "sort_order": self.order(values.sort_order),
            "actor_id": values.actor_id,
        }

    def changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {"reference", "attributes", "sort_order", "is_active"}
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "reference" in result:
            result["reference"] = self.reference(result["reference"])
        if "attributes" in result:
            attributes = self.attributes(result["attributes"])
            result["attributes"] = attributes
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        if "is_active" in result and not isinstance(result["is_active"], bool):
            raise _validation("is_active", "Active status must be true or false.")
        return result

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
            normalized_name, normalized_value = (
                " ".join(name.split()),
                " ".join(attribute_value.split()),
            )
            if (
                not 1 <= len(normalized_name) <= 50
                or not 1 <= len(normalized_value) <= 100
            ):
                raise _validation(
                    "attributes", "Attribute key or value length is invalid."
                )
            key = re.sub(r"[^a-z0-9]+", "-", normalized_name.casefold()).strip("-")
            if key in result:
                raise _validation("attributes", "Attribute names must be unique.")
            result[key] = normalized_value
        return dict(sorted(result.items()))

    @staticmethod
    def signature(value_ids: Sequence[UUID]) -> str:
        return normalized_attribute_signature(value_ids)

    @staticmethod
    def order(value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise _validation("sort_order", "Sort order must be non-negative.")
        return value


class ProductVariantService:
    def __init__(
        self, repository: ProductVariantRepository, outbox: OutboxService
    ) -> None:
        self._repository = repository
        self._outbox = outbox
        self._validation = ProductVariantValidationService()

    async def create(
        self, product_id: UUID, values: ProductVariantCreate
    ) -> ProductVariant:
        store_id = await self._repository.product_store(product_id, values.actor_id)
        if store_id is None:
            raise _not_found()
        validated = self._validation.create(values)
        requested_attributes = validated["attributes"]
        if not isinstance(requested_attributes, Mapping):
            raise _validation("attributes", "Variant Attributes are invalid.")
        attributes = await self._repository.resolve_attribute_values(
            store_id, requested_attributes
        )
        if attributes is None:
            raise _validation(
                "attributes", "Every Variant Attribute must map to an active value."
            )
        value_ids = [item.get("value_id") for item in attributes]
        if not value_ids or not all(
            isinstance(value_id, UUID) for value_id in value_ids
        ):
            raise _validation("attributes", "Normalized Attribute Values are invalid.")
        normalized_ids = [
            value_id for value_id in value_ids if isinstance(value_id, UUID)
        ]
        signature = self._validation.signature(normalized_ids)
        validated.pop("attributes")
        if await self._repository.reference_exists(
            store_id, str(validated["reference"])
        ):
            raise _conflict("Variant reference already exists in this Store.")
        if await self._repository.signature_exists(product_id, signature):
            raise _conflict("A variant with these attributes already exists.")
        variant = await self._repository.add(
            {
                **validated,
                "attribute_value_ids": normalized_ids,
                "product_id": product_id,
                "store_id": store_id,
                "attribute_signature": signature,
            }
        )
        PRODUCT_VARIANTS_CREATED.inc()
        await self._outbox.write(
            VariantCreated(
                aggregate_id=variant.id,
                store_id=variant.store_id,
                product_id=variant.product_id,
                variant_id=variant.id,
                version=variant.version,
            )
        )
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
        changes = self._validation.changes(values.values)
        if "reference" in changes and await self._repository.reference_exists(
            existing.store_id, str(changes["reference"]), exclude_id=variant_id
        ):
            raise _conflict("Variant reference already exists in this Store.")
        if "attributes" in changes:
            requested = changes.pop("attributes")
            if not isinstance(requested, Mapping):
                raise _validation("attributes", "Variant Attributes are invalid.")
            resolved = await self._repository.resolve_attribute_values(
                existing.store_id, requested
            )
            if resolved is None:
                raise _validation(
                    "attributes", "Every Variant Attribute must map to an active value."
                )
            value_ids = [item.get("value_id") for item in resolved]
            if not value_ids or not all(
                isinstance(value_id, UUID) for value_id in value_ids
            ):
                raise _validation(
                    "attributes", "Normalized Attribute Values are invalid."
                )
            normalized_ids = [
                value_id for value_id in value_ids if isinstance(value_id, UUID)
            ]
            signature = self._validation.signature(normalized_ids)
            if await self._repository.signature_exists(
                product_id, signature, exclude_id=variant_id
            ):
                raise _conflict("A variant with these attributes already exists.")
            changes["attribute_signature"] = signature
            changes["attribute_value_ids"] = normalized_ids
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
        await self._outbox.write(
            VariantUpdated(
                aggregate_id=variant.id,
                store_id=variant.store_id,
                product_id=variant.product_id,
                variant_id=variant.id,
                version=variant.version,
            )
        )
        if existing.is_active and not variant.is_active:
            await self._outbox.write(
                VariantArchived(
                    aggregate_id=variant.id,
                    store_id=variant.store_id,
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    version=variant.version,
                )
            )
        return variant

    async def delete_owned(
        self, variant_id: UUID, product_id: UUID, owner_id: UUID, version: int
    ) -> None:
        existing = await self._repository.get_for_owner(
            variant_id, product_id, owner_id
        )
        if existing is None:
            raise _not_found()
        archived = await self._repository.archive(
            variant_id,
            product_id,
            owner_id,
            expected_version=version,
            deleted_at=datetime.now(UTC),
        )
        if archived is None:
            raise _conflict("The variant was modified by another request.")
        PRODUCT_VARIANTS_DELETED.inc()
        if existing.is_active:
            await self._outbox.write(
                VariantArchived(
                    aggregate_id=archived.id,
                    store_id=archived.store_id,
                    product_id=archived.product_id,
                    variant_id=archived.id,
                    version=archived.version,
                )
            )
        await self._outbox.write(
            VariantDeleted(
                aggregate_id=archived.id,
                store_id=archived.store_id,
                product_id=archived.product_id,
                variant_id=archived.id,
                version=archived.version,
            )
        )


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
