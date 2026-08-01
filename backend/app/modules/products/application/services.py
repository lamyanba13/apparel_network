import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.products.application.repositories import ProductRepository
from app.modules.products.application.schemas import ProductCreate, ProductUpdate
from app.modules.products.domain import (
    Product,
    ProductArchived,
    ProductCreated,
    ProductDeleted,
    ProductStatus,
    ProductUpdated,
)
from app.observability.metrics import (
    PRODUCTS_ARCHIVED,
    PRODUCTS_CREATED,
    PRODUCTS_DELETED,
    PRODUCTS_UPDATED,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProductValidationService:
    def validate_create(self, values: ProductCreate) -> ProductCreate:
        if values.status is not ProductStatus.DRAFT:
            raise _validation("status", "Products must be created as draft.")
        return ProductCreate(
            values.catalog_id,
            self.text(values.name, "name", 2, 200),
            self.slug(values.slug),
            self.optional(values.short_description, 500),
            self.optional(values.description, 5000),
            values.status,
            values.visibility,
            self.sku(values.sku),
            self.optional(values.brand, 150),
            self.order(values.sort_order),
            values.actor_id,
        )

    def validate_changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "name",
            "slug",
            "short_description",
            "description",
            "visibility",
            "sku",
            "brand",
            "sort_order",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "name" in result:
            result["name"] = self.text(result["name"], "name", 2, 200)
        if "slug" in result:
            result["slug"] = self.slug(result["slug"])
        if "short_description" in result:
            result["short_description"] = self.optional(
                result["short_description"], 500
            )
        if "description" in result:
            result["description"] = self.optional(result["description"], 5000)
        if "brand" in result:
            result["brand"] = self.optional(result["brand"], 150)
        if "sku" in result:
            result["sku"] = self.sku(result["sku"])
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        return result

    @staticmethod
    def text(value: object, field: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            raise _validation(field, f"{field} must be text.")
        value = " ".join(value.split())
        if not minimum <= len(value) <= maximum:
            raise _validation(field, f"{field} length is invalid.")
        return value

    @staticmethod
    def optional(value: object, maximum: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > maximum:
            raise _validation("description", "Text length is invalid.")
        return " ".join(value.split()) or None

    @staticmethod
    def slug(value: object) -> str:
        if not isinstance(value, str):
            raise _validation("slug", "Slug is invalid.")
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode()
            .lower()
            .strip()
        )
        value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
        if len(value) > 180 or not _SLUG.fullmatch(value):
            raise _validation("slug", "Slug is invalid.")
        return value

    @staticmethod
    def sku(value: object) -> str:
        if not isinstance(value, str) or not _SKU.fullmatch(value.strip()):
            raise _validation("sku", "SKU format is invalid.")
        return value.strip().upper()

    @staticmethod
    def order(value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise _validation("sort_order", "Sort order must be non-negative.")
        return value


class ProductService:
    def __init__(self, repository: ProductRepository, events: EventPublisher) -> None:
        self._repository = repository
        self._events = events
        self._validation = ProductValidationService()

    async def create(self, values: ProductCreate) -> Product:
        validated = self._validation.validate_create(values)
        store_id = await self._repository.catalog_store(
            validated.catalog_id, validated.actor_id
        )
        if store_id is None:
            raise _not_found()
        if await self._repository.slug_exists(validated.catalog_id, validated.slug):
            raise _conflict("Product slug already exists in this Catalog.")
        if await self._repository.sku_exists(store_id, validated.sku):
            raise _conflict("Product SKU already exists in this Store.")
        product = await self._repository.add(
            {**asdict(validated), "store_id": store_id}
        )
        PRODUCTS_CREATED.inc()
        await self._events.publish(
            ProductCreated(
                product_id=product.id,
                catalog_id=product.catalog_id,
                store_id=product.store_id,
                version=product.version,
            )
        )
        return product

    async def list_owned(
        self, owner_id: UUID, **filters: object
    ) -> tuple[Sequence[Product], int]:
        return await self._repository.list_for_owner(owner_id, **filters)  # type: ignore[arg-type]

    async def get_owned(self, product_id: UUID, owner_id: UUID) -> Product:
        product = await self._repository.get_for_owner(product_id, owner_id)
        if product is None:
            raise _not_found()
        return product

    async def update_owned(
        self, product_id: UUID, owner_id: UUID, values: ProductUpdate
    ) -> Product:
        changes = self._validation.validate_changes(values.values)
        existing = await self.get_owned(product_id, owner_id)
        if "slug" in changes and await self._repository.slug_exists(
            existing.catalog_id, str(changes["slug"]), exclude_id=product_id
        ):
            raise _conflict("Product slug already exists in this Catalog.")
        if "sku" in changes and await self._repository.sku_exists(
            existing.store_id, str(changes["sku"]), exclude_id=product_id
        ):
            raise _conflict("Product SKU already exists in this Store.")
        product = await self._repository.update(
            product_id,
            owner_id,
            values=changes,
            expected_version=values.expected_version,
        )
        if product is None:
            raise _conflict("The product was modified by another request.")
        PRODUCTS_UPDATED.inc()
        await self._events.publish(
            ProductUpdated(
                product_id=product.id,
                catalog_id=product.catalog_id,
                store_id=product.store_id,
                version=product.version,
            )
        )
        return product

    async def delete_owned(
        self, product_id: UUID, owner_id: UUID, version: int
    ) -> None:
        product = await self._repository.archive(
            product_id, owner_id, expected_version=version, deleted_at=datetime.now(UTC)
        )
        if product is None:
            raise _not_found()
        PRODUCTS_DELETED.inc()
        await self._events.publish(
            ProductDeleted(
                product_id=product.id,
                catalog_id=product.catalog_id,
                store_id=product.store_id,
                version=product.version,
            )
        )


class ProductLifecycleService:
    def __init__(self, repository: ProductRepository, events: EventPublisher) -> None:
        self._repository, self._events = repository, events

    async def activate(self, product_id: UUID, owner_id: UUID, version: int) -> Product:
        return await self._transition(
            product_id, owner_id, ProductStatus.ACTIVE, version
        )

    async def archive(self, product_id: UUID, owner_id: UUID, version: int) -> Product:
        product = await self._transition(
            product_id, owner_id, ProductStatus.ARCHIVED, version
        )
        PRODUCTS_ARCHIVED.inc()
        await self._events.publish(
            ProductArchived(
                product_id=product.id,
                catalog_id=product.catalog_id,
                store_id=product.store_id,
                version=product.version,
            )
        )
        return product

    async def _transition(
        self, product_id: UUID, owner_id: UUID, status: ProductStatus, version: int
    ) -> Product:
        existing = await self._repository.get_for_owner(product_id, owner_id)
        if existing is None:
            raise _not_found()
        if (
            existing.status is ProductStatus.ARCHIVED
            and status is not ProductStatus.ARCHIVED
        ):
            raise _conflict("Archived products cannot be reactivated.")
        product = await self._repository.transition(
            product_id, owner_id, status=status, expected_version=version
        )
        if product is None:
            raise _conflict("The product was modified by another request.")
        return product


class ProductAuditService:
    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(self, event: object) -> None:
        await self._events.publish(event)  # type: ignore[arg-type]


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Product validation failed",
        detail="Product fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_product_field", message=message)],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Product not found",
        detail="The requested Product was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Product conflict",
        detail=detail,
        status_code=409,
    )
