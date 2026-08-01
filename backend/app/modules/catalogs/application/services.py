from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.catalogs.application.repositories import CatalogRepository
from app.modules.catalogs.application.schemas import CatalogCreate, CatalogUpdate
from app.modules.catalogs.domain import (
    Catalog,
    CatalogArchived,
    CatalogCreated,
    CatalogDeleted,
    CatalogStatus,
    CatalogUpdated,
)
from app.observability.metrics import (
    CATALOGS_ARCHIVED,
    CATALOGS_CREATED,
    CATALOGS_DELETED,
    CATALOGS_UPDATED,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESERVED_SLUGS = {"admin", "api", "search", "new", "null", "default", "system"}


class CatalogValidationService:
    def validate_create(self, values: CatalogCreate) -> CatalogCreate:
        if values.status is not CatalogStatus.DRAFT:
            raise _validation("status", "Catalogs must be created as draft.")
        if values.is_default:
            raise _validation("is_default", "Only active catalogs can be default.")
        return CatalogCreate(
            store_id=values.store_id,
            name=self.text(values.name, "name", 2, 150),
            slug=self.slug(values.slug),
            description=self.description(values.description),
            status=values.status,
            visibility=values.visibility,
            sort_order=self.order(values.sort_order),
            actor_id=values.actor_id,
            is_default=values.is_default,
        )

    def validate_changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "name",
            "slug",
            "description",
            "visibility",
            "sort_order",
            "is_default",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "name" in result:
            result["name"] = self.text(result["name"], "name", 2, 150)
        if "slug" in result:
            result["slug"] = self.slug(result["slug"])
        if "description" in result:
            result["description"] = self.description(result["description"])
        if "sort_order" in result:
            result["sort_order"] = self.order(result["sort_order"])
        return result

    @staticmethod
    def text(value: object, field: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            raise _validation(field, f"{field} must be text.")
        normalized = " ".join(value.split())
        if not minimum <= len(normalized) <= maximum:
            raise _validation(
                field, f"{field} must contain {minimum} to {maximum} characters."
            )
        return normalized

    @staticmethod
    def slug(value: object) -> str:
        if not isinstance(value, str):
            raise _validation("slug", "Slug must use lowercase canonical format.")
        normalized = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode()
            .lower()
            .strip()
        )
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        if len(normalized) > 180 or not _SLUG.fullmatch(normalized):
            raise _validation("slug", "Slug must use lowercase canonical format.")
        if normalized in _RESERVED_SLUGS:
            raise _validation("slug", "This slug is reserved.")
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
        if not isinstance(value, int) or value < 0:
            raise _validation("sort_order", "Sort order must be non-negative.")
        return value


class CatalogService:
    def __init__(self, repository: CatalogRepository, events: EventPublisher) -> None:
        self._repository = repository
        self._events = events
        self._validation = CatalogValidationService()

    async def create(self, values: CatalogCreate) -> Catalog:
        validated = self._validation.validate_create(values)
        if not await self._repository.store_owned(
            validated.store_id, validated.actor_id
        ):
            raise _not_found()
        if await self._repository.slug_exists(validated.store_id, validated.slug):
            raise _conflict("Catalog slug already exists for this Store.")
        catalog = await self._repository.add(asdict(validated))
        CATALOGS_CREATED.inc()
        await self._events.publish(
            CatalogCreated(
                catalog_id=catalog.id,
                store_id=catalog.store_id,
                version=catalog.version,
            )
        )
        return catalog

    async def list_owned(
        self, owner_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[Catalog], int]:
        return await self._repository.list_for_owner(
            owner_id, offset=offset, limit=limit
        )

    async def get_owned(self, catalog_id: UUID, owner_id: UUID) -> Catalog:
        catalog = await self._repository.get_for_owner(catalog_id, owner_id)
        if catalog is None:
            raise _not_found()
        return catalog

    async def update_owned(
        self, catalog_id: UUID, owner_id: UUID, values: CatalogUpdate
    ) -> Catalog:
        changes = self._validation.validate_changes(values.values)
        existing = await self._repository.get_for_owner(catalog_id, owner_id)
        if existing is None:
            raise _not_found()
        if "slug" in changes and await self._repository.slug_exists(
            existing.store_id,
            str(changes["slug"]),
            exclude_id=catalog_id,
        ):
            raise _conflict("Catalog slug already exists for this Store.")
        catalog = await self._repository.update(
            catalog_id,
            owner_id,
            values=changes,
            expected_version=values.expected_version,
        )
        if catalog is None:
            existing = await self._repository.get_for_owner(catalog_id, owner_id)
            if existing is None:
                raise _not_found()
            raise _conflict("The catalog was modified by another request.")
        CATALOGS_UPDATED.inc()
        await self._events.publish(
            CatalogUpdated(
                catalog_id=catalog.id,
                store_id=catalog.store_id,
                version=catalog.version,
            )
        )
        return catalog

    async def delete_owned(
        self, catalog_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        catalog = await self._repository.archive(
            catalog_id,
            owner_id,
            expected_version=expected_version,
            deleted_at=datetime.now(UTC),
        )
        if catalog is None:
            raise _not_found()
        CATALOGS_DELETED.inc()
        await self._events.publish(
            CatalogDeleted(
                catalog_id=catalog.id,
                store_id=catalog.store_id,
                version=catalog.version,
            )
        )


class CatalogLifecycleService:
    def __init__(self, repository: CatalogRepository, events: EventPublisher) -> None:
        self._repository = repository
        self._events = events

    async def activate(
        self, catalog_id: UUID, owner_id: UUID, expected_version: int
    ) -> Catalog:
        return await self._transition(
            catalog_id, owner_id, CatalogStatus.ACTIVE, expected_version
        )

    async def archive(
        self, catalog_id: UUID, owner_id: UUID, expected_version: int
    ) -> Catalog:
        catalog = await self._transition(
            catalog_id, owner_id, CatalogStatus.ARCHIVED, expected_version
        )
        CATALOGS_ARCHIVED.inc()
        await self._events.publish(
            CatalogArchived(
                catalog_id=catalog.id,
                store_id=catalog.store_id,
                version=catalog.version,
            )
        )
        return catalog

    async def _transition(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        status: CatalogStatus,
        expected_version: int,
    ) -> Catalog:
        existing = await self._repository.get_for_owner(catalog_id, owner_id)
        if existing is None:
            raise _not_found()
        if (
            existing.status is CatalogStatus.ARCHIVED
            and status is not CatalogStatus.ARCHIVED
        ):
            raise _conflict("Archived catalogs cannot be reactivated.")
        catalog = await self._repository.transition(
            catalog_id, owner_id, status=status, expected_version=expected_version
        )
        if catalog is None:
            raise _conflict("The catalog was modified by another request.")
        return catalog


class CatalogAuditService:
    """Stable audit boundary; domain events carry only safe identifiers."""

    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(self, event: object) -> None:
        await self._events.publish(event)  # type: ignore[arg-type]


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Catalog validation failed",
        detail="Catalog fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_catalog_field", message=message)],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Catalog not found",
        detail="The requested Catalog was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Catalog conflict",
        detail=detail,
        status_code=409,
    )
