import re
from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.catalogs.domain.taxonomy import (
    Category,
    CategoryStatus,
    Collection,
    CollectionStatus,
)
from app.modules.catalogs.domain.taxonomy_events import (
    CategoryCreated,
    CategoryDeleted,
    CategoryUpdated,
    CollectionCreated,
    CollectionDeleted,
    CollectionReordered,
    CollectionUpdated,
    ProductAssignedToCategory,
    ProductAssignedToCollection,
    ProductRemovedFromCategory,
    ProductRemovedFromCollection,
)
from app.observability.metrics import (
    CATEGORIES_CREATED,
    CATEGORIES_DELETED,
    COLLECTIONS_CREATED,
    COLLECTIONS_DELETED,
    PRODUCT_CATEGORY_ASSIGNMENTS,
    PRODUCT_COLLECTION_ASSIGNMENTS,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESERVED_SLUGS = {"new", "sale", "admin", "api", "featured", "search", "default"}


class TaxonomyValidationService:
    @staticmethod
    def text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise _validation(field, "Value must be text.")
        value = " ".join(value.split())
        if not value or len(value) > maximum:
            raise _validation(field, "Value length is invalid.")
        return value

    @staticmethod
    def slug(value: object) -> str:
        if not isinstance(value, str):
            raise _validation("slug", "Slug is invalid.")
        value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if not value or len(value) > 180 or not _SLUG.fullmatch(value):
            raise _validation("slug", "Slug is invalid.")
        if value in _RESERVED_SLUGS:
            raise _validation("slug", "Slug is reserved.")
        return value


class HierarchyService:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    async def validate_parent(
        self, category_id: UUID | None, parent_id: UUID | None, store_id: UUID
    ) -> None:
        if parent_id is None:
            return
        if category_id == parent_id or not await self._repository.category_in_store(
            parent_id, store_id
        ):
            raise _validation(
                "parent_category_id",
                "Category hierarchy would be circular or cross-store.",
            )
        seen: set[UUID] = set()
        current = parent_id
        while current is not None:
            if current in seen or current == category_id:
                raise _validation(
                    "parent_category_id", "Category hierarchy contains a cycle."
                )
            seen.add(current)
            current = await self._repository.parent_id(current)


class CategoryService:
    def __init__(self, repository: Any, events: EventPublisher) -> None:
        self.repository, self.events = repository, events
        self.validation = TaxonomyValidationService()
        self.hierarchy = HierarchyService(repository)

    async def create(self, values: Mapping[str, object], owner_id: UUID) -> Category:
        store_id = UUID(str(values["store_id"]))
        if not await self.repository.store_owned(store_id, owner_id):
            raise _not_found()
        await self.hierarchy.validate_parent(
            None, cast(UUID | None, values.get("parent_category_id")), store_id
        )
        data = {
            **values,
            "store_id": store_id,
            "name": self.validation.text(values["name"], "name", 150),
            "slug": self.validation.slug(values["slug"]),
        }
        if await self.repository.slug_exists(store_id, data["slug"]):
            raise _conflict("Category slug already exists.")
        category = await self.repository.add_category(data, owner_id)
        CATEGORIES_CREATED.inc()
        await self.events.publish(
            CategoryCreated(
                entity_id=category.id, store_id=store_id, version=category.version
            )
        )
        return category  # type: ignore[no-any-return]

    async def list(self, owner_id: UUID) -> Sequence[Category]:
        return await self.repository.list_categories(owner_id)  # type: ignore[no-any-return]

    async def get(self, entity_id: UUID, owner_id: UUID) -> Category:
        value = await self.repository.get_category(entity_id, owner_id)
        if value is None:
            raise _not_found()
        return value  # type: ignore[no-any-return]

    async def update(
        self,
        entity_id: UUID,
        owner_id: UUID,
        values: Mapping[str, object],
        version: int,
    ) -> Category:
        existing = await self.get(entity_id, owner_id)
        changes = dict(values)
        if "parent_category_id" in changes:
            await self.hierarchy.validate_parent(
                entity_id,
                cast(UUID | None, changes["parent_category_id"]),
                existing.store_id,
            )
        if "slug" in changes:
            changes["slug"] = self.validation.slug(changes["slug"])
            if await self.repository.slug_exists(
                existing.store_id, changes["slug"], entity_id
            ):
                raise _conflict("Category slug already exists.")
        if "name" in changes:
            changes["name"] = self.validation.text(changes["name"], "name", 150)
        value = await self.repository.update_category(
            entity_id, owner_id, changes, version
        )
        if value is None:
            raise _conflict("Category was modified by another request.")
        await self.events.publish(
            CategoryUpdated(
                entity_id=value.id, store_id=value.store_id, version=value.version
            )
        )
        return value  # type: ignore[no-any-return]

    async def delete(self, entity_id: UUID, owner_id: UUID, version: int) -> None:
        value = await self.repository.archive_category(entity_id, owner_id, version)
        if value is None:
            raise _not_found()
        CATEGORIES_DELETED.inc()
        await self.events.publish(
            CategoryDeleted(
                entity_id=value.id, store_id=value.store_id, version=value.version
            )
        )

    async def assign(self, entity_id: UUID, product_id: UUID, owner_id: UUID) -> None:
        category = await self.get(entity_id, owner_id)
        if (
            category.status is CategoryStatus.ARCHIVED
            or not await self.repository.product_in_store(product_id, category.store_id)
        ):
            raise _not_found()
        await self.repository.assign_category(entity_id, product_id)
        PRODUCT_CATEGORY_ASSIGNMENTS.inc()
        await self.events.publish(
            ProductAssignedToCategory(
                entity_id=product_id,
                store_id=category.store_id,
                version=category.version,
            )
        )

    async def remove(self, entity_id: UUID, product_id: UUID, owner_id: UUID) -> None:
        category = await self.get(entity_id, owner_id)
        await self.repository.remove_category(entity_id, product_id)
        await self.events.publish(
            ProductRemovedFromCategory(
                entity_id=product_id,
                store_id=category.store_id,
                version=category.version,
            )
        )


class CollectionService:
    def __init__(self, repository: Any, events: EventPublisher) -> None:
        self.repository, self.events, self.validation = (
            repository,
            events,
            TaxonomyValidationService(),
        )

    async def create(self, values: Mapping[str, object], owner_id: UUID) -> Collection:
        store_id = UUID(str(values["store_id"]))
        if not await self.repository.store_owned(store_id, owner_id):
            raise _not_found()
        data = {
            **values,
            "store_id": store_id,
            "name": self.validation.text(values["name"], "name", 150),
            "slug": self.validation.slug(values["slug"]),
        }
        if await self.repository.collection_slug_exists(store_id, data["slug"]):
            raise _conflict("Collection slug already exists.")
        value = await self.repository.add_collection(data, owner_id)
        COLLECTIONS_CREATED.inc()
        await self.events.publish(
            CollectionCreated(
                entity_id=value.id, store_id=store_id, version=value.version
            )
        )
        return value  # type: ignore[no-any-return]

    async def list(self, owner_id: UUID) -> Sequence[Collection]:
        return await self.repository.list_collections(owner_id)  # type: ignore[no-any-return]

    async def get(self, entity_id: UUID, owner_id: UUID) -> Collection:
        value = await self.repository.get_collection(entity_id, owner_id)
        if value is None:
            raise _not_found()
        return value  # type: ignore[no-any-return]

    async def update(
        self,
        entity_id: UUID,
        owner_id: UUID,
        values: Mapping[str, object],
        version: int,
    ) -> Collection:
        existing = await self.get(entity_id, owner_id)
        changes = dict(values)
        if "slug" in changes:
            changes["slug"] = self.validation.slug(changes["slug"])
            if await self.repository.collection_slug_exists(
                existing.store_id, changes["slug"], entity_id
            ):
                raise _conflict("Collection slug already exists.")
        if "name" in changes:
            changes["name"] = self.validation.text(changes["name"], "name", 150)
        value = await self.repository.update_collection(
            entity_id, owner_id, changes, version
        )
        if value is None:
            raise _conflict("Collection was modified by another request.")
        await self.events.publish(
            CollectionUpdated(
                entity_id=value.id, store_id=value.store_id, version=value.version
            )
        )
        return value  # type: ignore[no-any-return]

    async def delete(self, entity_id: UUID, owner_id: UUID, version: int) -> None:
        value = await self.repository.archive_collection(entity_id, owner_id, version)
        if value is None:
            raise _not_found()
        COLLECTIONS_DELETED.inc()
        await self.events.publish(
            CollectionDeleted(
                entity_id=value.id, store_id=value.store_id, version=value.version
            )
        )

    async def assign(self, entity_id: UUID, product_id: UUID, owner_id: UUID) -> None:
        collection = await self.get(entity_id, owner_id)
        if (
            collection.status is CollectionStatus.ARCHIVED
            or not await self.repository.product_in_store(
                product_id, collection.store_id
            )
        ):
            raise _not_found()
        await self.repository.assign_collection(entity_id, product_id)
        PRODUCT_COLLECTION_ASSIGNMENTS.inc()
        await self.events.publish(
            ProductAssignedToCollection(
                entity_id=product_id,
                store_id=collection.store_id,
                version=collection.version,
            )
        )

    async def remove(self, entity_id: UUID, product_id: UUID, owner_id: UUID) -> None:
        collection = await self.get(entity_id, owner_id)
        await self.repository.remove_collection(entity_id, product_id)
        await self.events.publish(
            ProductRemovedFromCollection(
                entity_id=product_id,
                store_id=collection.store_id,
                version=collection.version,
            )
        )

    async def reorder(
        self, entity_id: UUID, owner_id: UUID, product_ids: Sequence[UUID], version: int
    ) -> Collection:
        value = await self.repository.reorder_collection(
            entity_id, owner_id, product_ids, version
        )
        if value is None:
            raise _conflict("Collection was modified by another request.")
        await self.events.publish(
            CollectionReordered(
                entity_id=value.id, store_id=value.store_id, version=value.version
            )
        )
        return value  # type: ignore[no-any-return]


class AuditService:
    def __init__(self, events: EventPublisher) -> None:
        self.events = events

    async def publish(self, event: object) -> None:
        await self.events.publish(event)  # type: ignore[arg-type]


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Taxonomy validation failed",
        detail="Category or Collection fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_taxonomy_field", message=message)
        ],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Resource not found",
        detail="The requested resource was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Taxonomy conflict",
        detail=detail,
        status_code=409,
    )
