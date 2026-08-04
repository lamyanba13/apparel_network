from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.products.application.attribute_repositories import (
    AttributeRepository,
    AttributeValueRepository,
    OutboxRepository,
    VariantAttributeRepository,
)
from app.modules.products.application.attribute_schemas import (
    AttributeAssignment,
    AttributeCreate,
    AttributeUpdate,
    AttributeValueCreate,
    AttributeValueUpdate,
)
from app.modules.products.domain import (
    AttributeStatus,
    AttributeType,
    OutboxEvent,
    ProductAttribute,
    ProductAttributeValue,
    VariantAttributeAssigned,
    VariantAttributeAssignment,
    VariantAttributeRemoved,
    VariantAttributeValue,
)
from app.modules.products.domain.variant_events import VariantEvent
from app.observability.metrics import (
    ATTRIBUTE_VALUES_CREATED,
    ATTRIBUTES_CREATED,
    OUTBOX_WRITTEN,
    VARIANT_ATTRIBUTES_ASSIGNED,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class AttributeValidationService:
    def create(self, values: AttributeCreate) -> dict[str, object]:
        if values.status is not AttributeStatus.ACTIVE:
            raise _validation("status", "Attributes must be created as active.")
        result = asdict(values)
        result["name"] = self.text(values.name, "name", 1, 150)
        result["slug"] = self.slug(values.slug, "slug", 180)
        result["description"] = self.description(values.description)
        result["sort_order"] = self.order(values.sort_order)
        return result

    def changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "name",
            "slug",
            "description",
            "required",
            "filterable",
            "searchable",
            "sort_order",
            "status",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "name" in result:
            result["name"] = self.text(result["name"], "name", 1, 150)
        if "slug" in result:
            result["slug"] = self.slug(result["slug"], "slug", 180)
        if "description" in result:
            result["description"] = self.description(result["description"])
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        for field in ("required", "filterable", "searchable"):
            if field in result and not isinstance(result[field], bool):
                raise _validation(field, f"{field} must be true or false.")
        if "status" in result and not isinstance(result["status"], AttributeStatus):
            raise _validation("status", "Attribute status is invalid.")
        return result

    def value_create(
        self, values: AttributeValueCreate, attribute_type: AttributeType
    ) -> dict[str, object]:
        return {
            "value": self.typed_value(values.value, attribute_type),
            "slug": self.slug(values.slug, "slug", 200),
            "sort_order": self.order(values.sort_order),
        }

    def value_changes(
        self, values: Mapping[str, object], attribute_type: AttributeType
    ) -> dict[str, object]:
        if not values or not set(values) <= {"value", "slug", "sort_order"}:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "value" in result:
            if not isinstance(result["value"], str):
                raise _validation("value", "Attribute value must be text.")
            result["value"] = self.typed_value(result["value"], attribute_type)
        if "slug" in result:
            result["slug"] = self.slug(result["slug"], "slug", 200)
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        return result

    @staticmethod
    def text(value: object, field: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            raise _validation(field, f"{field} must be text.")
        normalized = " ".join(value.split())
        if not minimum <= len(normalized) <= maximum:
            raise _validation(field, f"{field} length is invalid.")
        return normalized

    @staticmethod
    def slug(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise _validation(field, f"{field} must use lowercase kebab-case.")
        normalized = value.strip().lower()
        if len(normalized) > maximum or not _SLUG.fullmatch(normalized):
            raise _validation(field, f"{field} must use lowercase kebab-case.")
        return normalized

    @staticmethod
    def description(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 2000:
            raise _validation(
                "description", "Description cannot exceed 2000 characters."
            )
        return " ".join(value.split()) or None

    @staticmethod
    def order(value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise _validation("sort_order", "Sort order must be non-negative.")
        return value

    def typed_value(self, value: str, attribute_type: AttributeType) -> str:
        normalized = self.text(value, "value", 1, 200)
        if attribute_type is AttributeType.NUMBER:
            try:
                number = Decimal(normalized)
            except InvalidOperation as error:
                raise _validation(
                    "value", "Number attributes require a decimal."
                ) from error
            if not number.is_finite():
                raise _validation(
                    "value", "Number attributes require a finite decimal."
                )
        elif attribute_type is AttributeType.BOOLEAN:
            normalized = normalized.lower()
            if normalized not in {"true", "false"}:
                raise _validation("value", "Boolean attributes require true or false.")
        elif attribute_type is AttributeType.DATE:
            try:
                date.fromisoformat(normalized)
            except ValueError as error:
                raise _validation(
                    "value", "Date attributes require ISO-8601 dates."
                ) from error
        elif attribute_type is AttributeType.COLOR and not _COLOR.fullmatch(normalized):
            raise _validation(
                "value", "Color attributes require a six-digit hex color."
            )
        return normalized


class AttributeService:
    def __init__(
        self,
        attributes: AttributeRepository,
        values: AttributeValueRepository,
    ) -> None:
        self._attributes = attributes
        self._values = values
        self._validation = AttributeValidationService()

    async def create(self, values: AttributeCreate) -> ProductAttribute:
        data = self._validation.create(values)
        if not await self._attributes.store_owned(values.store_id, values.actor_id):
            raise _not_found("Attribute")
        if await self._attributes.slug_exists(values.store_id, str(data["slug"])):
            raise _conflict("Attribute slug already exists for this Store.")
        attribute = await self._attributes.add(data)
        ATTRIBUTES_CREATED.inc()
        return attribute

    async def list_owned(
        self, owner_id: UUID, *, store_id: UUID | None = None
    ) -> Sequence[ProductAttribute]:
        if store_id is not None and not await self._attributes.store_owned(
            store_id, owner_id
        ):
            raise _not_found("Attribute")
        return await self._attributes.list_for_owner(owner_id, store_id=store_id)

    async def get_owned(self, attribute_id: UUID, owner_id: UUID) -> ProductAttribute:
        attribute = await self._attributes.get_for_owner(attribute_id, owner_id)
        if attribute is None:
            raise _not_found("Attribute")
        return attribute

    async def update_owned(
        self, attribute_id: UUID, owner_id: UUID, values: AttributeUpdate
    ) -> ProductAttribute:
        current = await self.get_owned(attribute_id, owner_id)
        changes = self._validation.changes(values.values)
        if (
            current.status is AttributeStatus.ARCHIVED
            and changes.get("status", current.status) is not AttributeStatus.ARCHIVED
        ):
            raise _conflict("Archived Attributes cannot be reactivated.")
        if "slug" in changes and await self._attributes.slug_exists(
            current.store_id, str(changes["slug"]), exclude_id=current.id
        ):
            raise _conflict("Attribute slug already exists for this Store.")
        updated = await self._attributes.update(
            attribute_id,
            owner_id,
            values={**changes, "updated_by_id": values.actor_id},
            expected_version=values.expected_version,
        )
        if updated is None:
            raise _conflict("The Attribute was modified by another request.")
        return updated

    async def delete_owned(
        self, attribute_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        await self.get_owned(attribute_id, owner_id)
        if (
            await self._attributes.archive(
                attribute_id,
                owner_id,
                expected_version=expected_version,
                deleted_at=datetime.now(UTC),
                deleted_by_id=owner_id,
            )
            is None
        ):
            raise _conflict("The Attribute was modified by another request.")

    async def create_value(
        self, attribute_id: UUID, owner_id: UUID, values: AttributeValueCreate
    ) -> ProductAttributeValue:
        attribute = await self.get_owned(attribute_id, owner_id)
        if attribute.status is not AttributeStatus.ACTIVE:
            raise _conflict("Archived Attributes cannot receive values.")
        data = self._validation.value_create(values, attribute.attribute_type)
        if await self._values.value_exists(attribute_id, str(data["value"])):
            raise _conflict("Attribute Value already exists.")
        if await self._values.slug_exists(attribute_id, str(data["slug"])):
            raise _conflict("Attribute Value slug already exists.")
        value = await self._values.add(attribute_id, data)
        ATTRIBUTE_VALUES_CREATED.inc()
        return value

    async def update_value(
        self, value_id: UUID, owner_id: UUID, values: AttributeValueUpdate
    ) -> ProductAttributeValue:
        current = await self._values.get_for_owner(value_id, owner_id)
        if current is None:
            raise _not_found("Attribute Value")
        attribute = await self.get_owned(current.attribute_id, owner_id)
        changes = self._validation.value_changes(
            values.values, attribute.attribute_type
        )
        if "value" in changes and await self._values.value_exists(
            current.attribute_id, str(changes["value"]), exclude_id=current.id
        ):
            raise _conflict("Attribute Value already exists.")
        if "slug" in changes and await self._values.slug_exists(
            current.attribute_id, str(changes["slug"]), exclude_id=current.id
        ):
            raise _conflict("Attribute Value slug already exists.")
        updated = await self._values.update(
            value_id,
            owner_id,
            values=changes,
            expected_version=values.expected_version,
        )
        if updated is None:
            raise _conflict("The Attribute Value was modified by another request.")
        return updated

    async def delete_value(
        self, value_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        if await self._values.get_for_owner(value_id, owner_id) is None:
            raise _not_found("Attribute Value")
        deleted = await self._values.delete(
            value_id, owner_id, expected_version=expected_version
        )
        if deleted is False:
            raise _conflict("Assigned Attribute Values cannot be deleted.")
        if deleted is None:
            raise _conflict("The Attribute Value was modified by another request.")


class OutboxService:
    def __init__(self, repository: OutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: VariantEvent) -> OutboxEvent:
        persisted = await self._repository.add(event)
        OUTBOX_WRITTEN.inc()
        return persisted


class VariantAttributeService:
    def __init__(
        self, repository: VariantAttributeRepository, outbox: OutboxService
    ) -> None:
        self._repository = repository
        self._outbox = outbox

    async def list_owned(
        self, variant_id: UUID, owner_id: UUID
    ) -> Sequence[VariantAttributeValue]:
        values = await self._repository.list_for_variant(variant_id, owner_id)
        if values is None:
            raise _not_found("Variant")
        return values

    async def assign(
        self, variant_id: UUID, owner_id: UUID, values: AttributeAssignment
    ) -> VariantAttributeAssignment:
        context = await self._repository.variant_context(variant_id, owner_id)
        value = await self._repository.value_context(
            values.attribute_value_id, owner_id
        )
        current = await self._repository.list_for_variant(variant_id, owner_id)
        if context is None or value is None or current is None:
            raise _not_found("Variant or Attribute Value")
        if context.get("store_id") != value.get("store_id"):
            raise _not_found("Variant or Attribute Value")
        attribute_id = value.get("attribute_id")
        if any(item.attribute_id == attribute_id for item in current):
            raise _conflict("The Variant already has a value for this Attribute.")
        value_ids = [item.value_id for item in current] + [values.attribute_value_id]
        signature = normalized_attribute_signature(value_ids)
        product_id = context.get("product_id")
        store_id = context.get("store_id")
        if not isinstance(product_id, UUID) or not isinstance(store_id, UUID):
            raise _not_found("Variant")
        if await self._repository.combination_exists(
            product_id, signature, exclude_id=variant_id
        ):
            raise _conflict("A Variant with this Attribute combination already exists.")
        assignment = await self._repository.assign(
            variant_id,
            values.attribute_value_id,
            owner_id,
            expected_version=values.expected_version,
            signature=signature,
        )
        if assignment is None:
            raise _conflict("The Variant was modified by another request.")
        VARIANT_ATTRIBUTES_ASSIGNED.inc()
        await self._outbox.write(
            VariantAttributeAssigned(
                aggregate_id=variant_id,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                version=values.expected_version + 1,
            )
        )
        return assignment

    async def remove(
        self,
        variant_id: UUID,
        value_id: UUID,
        owner_id: UUID,
        expected_version: int,
    ) -> None:
        context = await self._repository.variant_context(variant_id, owner_id)
        current = await self._repository.list_for_variant(variant_id, owner_id)
        if context is None or current is None:
            raise _not_found("Variant")
        remaining = [item.value_id for item in current if item.value_id != value_id]
        if len(remaining) == len(current):
            raise _not_found("Variant Attribute Assignment")
        if not remaining:
            raise _validation(
                "attribute_value_id", "Variants require at least one Attribute Value."
            )
        signature = normalized_attribute_signature(remaining)
        product_id = context.get("product_id")
        store_id = context.get("store_id")
        if not isinstance(product_id, UUID) or not isinstance(store_id, UUID):
            raise _not_found("Variant")
        if await self._repository.combination_exists(
            product_id, signature, exclude_id=variant_id
        ):
            raise _conflict("A Variant with this Attribute combination already exists.")
        assignment = await self._repository.remove(
            variant_id,
            value_id,
            owner_id,
            expected_version=expected_version,
            signature=signature,
        )
        if assignment is None:
            raise _conflict("The Variant was modified by another request.")
        await self._outbox.write(
            VariantAttributeRemoved(
                aggregate_id=variant_id,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                version=expected_version + 1,
            )
        )


def normalized_attribute_signature(value_ids: Sequence[UUID]) -> str:
    canonical = json.dumps(sorted(str(value_id) for value_id in value_ids))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Attribute validation failed",
        detail="Attribute fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_attribute", message=message)],
    )


def _not_found(subject: str) -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{subject} not found",
        detail=f"The requested {subject} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Attribute conflict",
        detail=detail,
        status_code=409,
    )
