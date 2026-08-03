from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter
from typing import cast
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.pricing.application.price_list_repositories import (
    AssignmentRepository,
    PriceListRepository,
    ResolverRepository,
)
from app.modules.pricing.application.price_list_schemas import (
    AssignPriceRequest,
    PriceListCreate,
    PriceListFilter,
    PriceListUpdate,
    ResolvePriceRequest,
)
from app.modules.pricing.application.services import ProductPriceValidationService
from app.modules.pricing.domain import (
    CustomerGroup,
    PriceAssigned,
    PriceAssignment,
    PriceList,
    PriceListArchived,
    PriceListCreated,
    PriceListStatus,
    PriceListUpdated,
    PriceResolved,
    PriceUnassigned,
    ResolvedPrice,
)
from app.modules.pricing.domain.price_list_events import PriceListEvent
from app.observability.metrics import (
    PRICE_LISTS_CREATED,
    PRICE_LISTS_UPDATED,
    PRICE_RESOLUTION_DURATION,
    PRICES_ASSIGNED,
    PRICES_RESOLVED,
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PriceListValidationService:
    def validate_create(self, values: PriceListCreate) -> dict[str, object]:
        if values.status is not PriceListStatus.DRAFT:
            raise _validation("status", "Price Lists must be created as draft.")
        if values.is_default:
            raise _validation("is_default", "Only active Price Lists can be default.")
        result = asdict(values)
        result["name"] = self.text(values.name, "name", 2, 150)
        result["slug"] = self.slug(values.slug)
        result["description"] = self.description(values.description)
        result["currency_code"] = ProductPriceValidationService.currency(
            values.currency_code
        )
        result["priority"] = self.priority(values.priority)
        self.period(values.effective_from, values.effective_until)
        return result

    def validate_changes(
        self, values: Mapping[str, object], current: PriceList
    ) -> dict[str, object]:
        allowed = {
            "name",
            "slug",
            "description",
            "priority",
            "status",
            "customer_group",
            "effective_from",
            "effective_until",
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
        if "priority" in result:
            result["priority"] = self.priority(result["priority"])
        if "status" in result and not isinstance(result["status"], PriceListStatus):
            raise _validation("status", "Price List status is invalid.")
        if "customer_group" in result and not isinstance(
            result["customer_group"], CustomerGroup
        ):
            raise _validation("customer_group", "Customer group is invalid.")
        if "is_default" in result and not isinstance(result["is_default"], bool):
            raise _validation("is_default", "Default flag is invalid.")
        start = result.get("effective_from", current.effective_from)
        end = result.get("effective_until", current.effective_until)
        if start is not None and not isinstance(start, datetime):
            raise _validation("effective_from", "Effective timestamp is invalid.")
        if end is not None and not isinstance(end, datetime):
            raise _validation("effective_until", "Effective timestamp is invalid.")
        self.period(start, end)
        status = result.get("status", current.status)
        group = result.get("customer_group", current.customer_group)
        default = result.get("is_default", current.is_default)
        if default and status is not PriceListStatus.ACTIVE:
            raise _validation("is_default", "Only active Price Lists can be default.")
        if default and group is not CustomerGroup.PUBLIC:
            raise _validation("is_default", "Default Price Lists must be public.")
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
            raise _validation("slug", "Slug must use lowercase kebab-case.")
        normalized = value.strip().lower()
        if len(normalized) > 180 or not _SLUG.fullmatch(normalized):
            raise _validation("slug", "Slug must use lowercase kebab-case.")
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
    def priority(value: object) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= 1_000_000
        ):
            raise _validation("priority", "Priority must be between 0 and 1000000.")
        return value

    @staticmethod
    def period(start: datetime | None, end: datetime | None) -> None:
        ProductPriceValidationService.period(start, end)

    def validate_filter(self, values: PriceListFilter) -> PriceListFilter:
        currency = (
            ProductPriceValidationService.currency(values.currency)
            if values.currency
            else None
        )
        if values.effective_at is not None and values.effective_at.utcoffset() is None:
            raise _validation(
                "effective_at", "Effective timestamp must include a timezone."
            )
        return PriceListFilter(
            store_id=values.store_id,
            currency=currency,
            status=values.status,
            customer_group=values.customer_group,
            effective_at=values.effective_at,
            offset=values.offset,
            limit=values.limit,
        )


class PriceListService:
    def __init__(
        self,
        repository: PriceListRepository,
        assignments: AssignmentRepository,
        events: EventPublisher,
    ) -> None:
        self._repository = repository
        self._assignments = assignments
        self._events = events
        self._validation = PriceListValidationService()

    async def create(self, values: PriceListCreate) -> PriceList:
        data = self._validation.validate_create(values)
        if not await self._repository.store_owned(values.store_id, values.actor_id):
            raise _not_found()
        if await self._repository.slug_exists(values.store_id, cast(str, data["slug"])):
            raise _conflict("Price List slug already exists for this Store.")
        price_list = await self._repository.add(data)
        PRICE_LISTS_CREATED.inc()
        await self._publish(PriceListCreated, price_list)
        return price_list

    async def list_owned(
        self, owner_id: UUID, filters: PriceListFilter
    ) -> tuple[Sequence[PriceList], int]:
        return await self._repository.list_for_owner(
            owner_id, self._validation.validate_filter(filters)
        )

    async def get_owned(self, price_list_id: UUID, owner_id: UUID) -> PriceList:
        price_list = await self._repository.get_for_owner(price_list_id, owner_id)
        if price_list is None:
            raise _not_found()
        return price_list

    async def update_owned(
        self, price_list_id: UUID, owner_id: UUID, values: PriceListUpdate
    ) -> PriceList:
        current = await self.get_owned(price_list_id, owner_id)
        changes = self._validation.validate_changes(values.values, current)
        target_status = cast(PriceListStatus, changes.get("status", current.status))
        self._validate_transition(current.status, target_status)
        if "slug" in changes and await self._repository.slug_exists(
            current.store_id, cast(str, changes["slug"]), exclude_id=current.id
        ):
            raise _conflict("Price List slug already exists for this Store.")
        is_default = cast(bool, changes.get("is_default", current.is_default))
        if is_default and await self._repository.default_exists(
            current.store_id, current.currency_code, exclude_id=current.id
        ):
            raise _conflict("A default Price List already exists for this currency.")
        updated = await self._repository.update(
            price_list_id,
            owner_id,
            values={**changes, "updated_by_id": values.actor_id},
            expected_version=values.expected_version,
        )
        if updated is None:
            if await self._repository.get_for_owner(price_list_id, owner_id) is None:
                raise _not_found()
            raise _conflict("The Price List was modified by another request.")
        PRICE_LISTS_UPDATED.inc()
        await self._publish(PriceListUpdated, updated)
        if (
            target_status is PriceListStatus.ARCHIVED
            and current.status is not target_status
        ):
            await self._publish(PriceListArchived, updated)
        return updated

    async def delete_owned(
        self, price_list_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        current = await self.get_owned(price_list_id, owner_id)
        archived = await self._repository.archive(
            price_list_id,
            owner_id,
            expected_version=expected_version,
            deleted_at=datetime.now(UTC),
            deleted_by_id=owner_id,
        )
        if archived is None:
            raise _conflict("The Price List was modified by another request.")
        if current.status is not PriceListStatus.ARCHIVED:
            await self._publish(PriceListArchived, archived)

    async def assign(
        self, price_list_id: UUID, owner_id: UUID, values: AssignPriceRequest
    ) -> PriceAssignment:
        price_list = await self.get_owned(price_list_id, owner_id)
        context = await self._assignments.price_context(values.price_id, owner_id)
        if (
            context is None
            or context.get("store_id") != price_list.store_id
            or context.get("currency_code") != price_list.currency_code
        ):
            raise _not_found()
        assignment = await self._assignments.add(
            price_list_id, values.price_id, values.actor_id
        )
        if assignment is None:
            raise _conflict("The price is already assigned to this Price List.")
        PRICES_ASSIGNED.inc()
        await self._events.publish(
            PriceAssigned(
                price_list_id=price_list.id,
                price_id=assignment.price_id,
                store_id=price_list.store_id,
                version=assignment.version,
            )
        )
        return assignment

    async def unassign(
        self, price_list_id: UUID, price_id: UUID, owner_id: UUID
    ) -> None:
        price_list = await self.get_owned(price_list_id, owner_id)
        assignment = await self._assignments.remove(price_list_id, price_id)
        if assignment is None:
            raise _not_found()
        await self._events.publish(
            PriceUnassigned(
                price_list_id=price_list.id,
                price_id=price_id,
                store_id=price_list.store_id,
                version=assignment.version,
            )
        )

    @staticmethod
    def _validate_transition(current: PriceListStatus, target: PriceListStatus) -> None:
        if current is PriceListStatus.ARCHIVED and target is not current:
            raise _conflict("Archived Price Lists cannot be reactivated.")
        if current is PriceListStatus.ACTIVE and target is PriceListStatus.DRAFT:
            raise _conflict("Active Price Lists cannot return to draft.")

    async def _publish(
        self, event_type: type[PriceListEvent], price_list: PriceList
    ) -> None:
        await self._events.publish(
            event_type(
                price_list_id=price_list.id,
                price_id=None,
                store_id=price_list.store_id,
                version=price_list.version,
            )
        )


class PricingResolver:
    def __init__(self, repository: ResolverRepository, events: EventPublisher) -> None:
        self._repository = repository
        self._events = events

    async def resolve(self, values: ResolvePriceRequest) -> ResolvedPrice:
        started = perf_counter()
        try:
            currency = ProductPriceValidationService.currency(values.currency)
            if values.timestamp.utcoffset() is None:
                raise _validation(
                    "timestamp", "Resolution timestamp requires a timezone."
                )
            if not await self._repository.context_owned(
                values.store_id,
                values.product_id,
                values.variant_id,
                values.actor_id,
            ):
                raise _not_found()
            resolved = await self._repository.resolve(
                store_id=values.store_id,
                product_id=values.product_id,
                variant_id=values.variant_id,
                currency_code=currency,
                customer_group=values.customer_group,
                timestamp=values.timestamp,
            )
            if resolved is None:
                raise _not_found("Resolved price")
            PRICES_RESOLVED.inc()
            await self._events.publish(
                PriceResolved(
                    price_list_id=resolved.price_list_id,
                    price_id=resolved.price_id,
                    store_id=resolved.store_id,
                    version=resolved.price_version,
                )
            )
            return resolved
        finally:
            PRICE_RESOLUTION_DURATION.observe(perf_counter() - started)


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Price List validation failed",
        detail="Price List fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_price_list", message=message)],
    )


def _not_found(subject: str = "Price List") -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{subject} not found",
        detail=f"The requested {subject} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Price List conflict",
        detail=detail,
        status_code=409,
    )
