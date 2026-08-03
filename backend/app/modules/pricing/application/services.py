from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.pricing.application.policies import PricingOwnershipPolicy
from app.modules.pricing.application.repositories import ProductPriceRepository
from app.modules.pricing.application.schemas import (
    ProductPriceCreate,
    ProductPriceFilter,
    ProductPriceUpdate,
)
from app.modules.pricing.domain import (
    Money,
    PriceStatus,
    ProductPrice,
    ProductPriceActivated,
    ProductPriceArchived,
    ProductPriceCreated,
    ProductPriceDeleted,
    ProductPriceUpdated,
)
from app.modules.pricing.domain.events import ProductPriceEvent
from app.observability.metrics import (
    PRICES_ACTIVATED,
    PRICES_CREATED,
    PRICES_DELETED,
    PRICES_UPDATED,
)

_TAX_CLASS = re.compile(r"^[a-z][a-z0-9_-]{0,49}$")


class ProductPriceValidationService:
    def validate_create(self, values: ProductPriceCreate) -> dict[str, object]:
        if values.status is not PriceStatus.DRAFT:
            raise _validation("status", "Prices must be created as draft.")
        result = asdict(values)
        result["currency_code"] = self.currency(values.currency_code)
        result["tax_class"] = self.tax_class(values.tax_class)
        self.prices(result, result["currency_code"])
        self.period(values.effective_from, values.effective_until)
        return result

    def validate_changes(
        self, values: Mapping[str, object], current: ProductPrice
    ) -> dict[str, object]:
        allowed = {
            "base_price",
            "sale_price",
            "compare_at_price",
            "cost_price",
            "tax_class",
            "status",
            "effective_from",
            "effective_until",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "tax_class" in result:
            result["tax_class"] = self.tax_class(result["tax_class"])
        if "status" in result and not isinstance(result["status"], PriceStatus):
            raise _validation("status", "Price status is invalid.")
        merged = {
            "base_price": current.base_price,
            "sale_price": current.sale_price,
            "compare_at_price": current.compare_at_price,
            "cost_price": current.cost_price,
            **result,
        }
        self.prices(merged, current.currency_code)
        effective_from = result.get("effective_from", current.effective_from)
        effective_until = result.get("effective_until", current.effective_until)
        if effective_from is not None and not isinstance(effective_from, datetime):
            raise _validation("effective_from", "Effective timestamp is invalid.")
        if effective_until is not None and not isinstance(effective_until, datetime):
            raise _validation("effective_until", "Effective timestamp is invalid.")
        self.period(effective_from, effective_until)
        return result

    @staticmethod
    def currency(value: object) -> str:
        if not isinstance(value, str):
            raise _validation("currency_code", "Currency code is invalid.")
        try:
            return Money(Decimal("0"), value).currency_code
        except ValueError as error:
            raise _validation("currency_code", str(error)) from error

    @staticmethod
    def tax_class(value: object) -> str:
        if not isinstance(value, str):
            raise _validation("tax_class", "Tax class is invalid.")
        normalized = value.strip().lower()
        if not _TAX_CLASS.fullmatch(normalized):
            raise _validation("tax_class", "Tax class must use canonical format.")
        return normalized

    @staticmethod
    def prices(values: Mapping[str, object], currency_code: object) -> None:
        if not isinstance(currency_code, str):
            raise _validation("currency_code", "Currency code is invalid.")
        normalized: dict[str, Decimal | None] = {}
        for field in ("base_price", "sale_price", "compare_at_price", "cost_price"):
            value = values.get(field)
            if value is None and field != "base_price":
                normalized[field] = None
                continue
            if not isinstance(value, Decimal):
                raise _validation(field, "Price must be a decimal amount.")
            try:
                normalized[field] = Money(value, currency_code).amount
            except ValueError as error:
                raise _validation(field, str(error)) from error
        base = normalized["base_price"]
        sale = normalized["sale_price"]
        compare_at = normalized["compare_at_price"]
        if base is None:
            raise _validation("base_price", "Base price is required.")
        if sale is not None and sale > base:
            raise _validation("sale_price", "Sale price cannot exceed base price.")
        if compare_at is not None and compare_at < base:
            raise _validation(
                "compare_at_price", "Compare-at price cannot be below base price."
            )

    @staticmethod
    def period(start: datetime | None, end: datetime | None) -> None:
        for field, value in (("effective_from", start), ("effective_until", end)):
            if value is not None and value.utcoffset() is None:
                raise _validation(
                    field, "Effective timestamps must include a timezone."
                )
        if start is not None and end is not None and start >= end:
            raise _validation(
                "effective_until", "Effective end must be after effective start."
            )

    def validate_filter(self, filters: ProductPriceFilter) -> ProductPriceFilter:
        currency = self.currency(filters.currency) if filters.currency else None
        if (
            filters.effective_at is not None
            and filters.effective_at.utcoffset() is None
        ):
            raise _validation(
                "effective_at", "Effective timestamp must include a timezone."
            )
        return ProductPriceFilter(
            store_id=filters.store_id,
            product_id=filters.product_id,
            variant_id=filters.variant_id,
            currency=currency,
            status=filters.status,
            effective_at=filters.effective_at,
            offset=filters.offset,
            limit=filters.limit,
        )


class PricingService:
    def __init__(
        self, repository: ProductPriceRepository, events: EventPublisher
    ) -> None:
        self._repository = repository
        self._events = events
        self._validation = ProductPriceValidationService()
        self._ownership = PricingOwnershipPolicy(repository)

    async def create(self, values: ProductPriceCreate) -> ProductPrice:
        persisted = self._validation.validate_create(values)
        if not await self._ownership.validate(
            store_id=values.store_id,
            product_id=values.product_id,
            variant_id=values.variant_id,
            owner_id=values.actor_id,
        ):
            raise _not_found()
        price = await self._repository.add(persisted)
        PRICES_CREATED.inc()
        await self._publish(ProductPriceCreated, price)
        return price

    async def list_owned(
        self, owner_id: UUID, filters: ProductPriceFilter
    ) -> tuple[Sequence[ProductPrice], int]:
        return await self._repository.list_for_owner(
            owner_id, self._validation.validate_filter(filters)
        )

    async def get_owned(self, price_id: UUID, owner_id: UUID) -> ProductPrice:
        price = await self._repository.get_for_owner(price_id, owner_id)
        if price is None:
            raise _not_found()
        return price

    async def update_owned(
        self, price_id: UUID, owner_id: UUID, values: ProductPriceUpdate
    ) -> ProductPrice:
        current = await self.get_owned(price_id, owner_id)
        changes = self._validation.validate_changes(values.values, current)
        target_status = changes.get("status", current.status)
        if not isinstance(target_status, PriceStatus):
            raise _validation("status", "Price status is invalid.")
        self._validate_transition(current.status, target_status)
        effective_from = changes.get("effective_from", current.effective_from)
        effective_until = changes.get("effective_until", current.effective_until)
        if (
            target_status is PriceStatus.ACTIVE
            and await self._repository.active_price_exists(
                product_id=current.product_id,
                variant_id=current.variant_id,
                currency_code=current.currency_code,
                effective_from=(
                    effective_from if isinstance(effective_from, datetime) else None
                ),
                effective_until=(
                    effective_until if isinstance(effective_until, datetime) else None
                ),
                exclude_id=current.id,
            )
        ):
            raise _conflict("An active price already exists for this effective period.")
        price = await self._repository.update(
            price_id,
            owner_id,
            values={**changes, "updated_by_id": values.actor_id},
            expected_version=values.expected_version,
        )
        if price is None:
            if await self._repository.get_for_owner(price_id, owner_id) is None:
                raise _not_found()
            raise _conflict("The product price was modified by another request.")
        PRICES_UPDATED.inc()
        await self._publish(ProductPriceUpdated, price)
        if current.status is not target_status:
            if target_status is PriceStatus.ACTIVE:
                PRICES_ACTIVATED.inc()
                await self._publish(ProductPriceActivated, price)
            elif target_status is PriceStatus.ARCHIVED:
                await self._publish(ProductPriceArchived, price)
        return price

    async def delete_owned(
        self, price_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        current = await self.get_owned(price_id, owner_id)
        price = await self._repository.archive(
            price_id,
            owner_id,
            expected_version=expected_version,
            deleted_at=datetime.now(UTC),
            deleted_by_id=owner_id,
        )
        if price is None:
            raise _conflict("The product price was modified by another request.")
        if current.status is not PriceStatus.ARCHIVED:
            await self._publish(ProductPriceArchived, price)
        PRICES_DELETED.inc()
        await self._publish(ProductPriceDeleted, price)

    @staticmethod
    def _validate_transition(current: PriceStatus, target: PriceStatus) -> None:
        if current is PriceStatus.ARCHIVED and target is not PriceStatus.ARCHIVED:
            raise _conflict("Archived prices cannot be reactivated.")
        if current is PriceStatus.DRAFT and target not in {
            PriceStatus.DRAFT,
            PriceStatus.ACTIVE,
            PriceStatus.ARCHIVED,
        }:
            raise _conflict("Invalid price lifecycle transition.")
        if current is PriceStatus.ACTIVE and target not in {
            PriceStatus.ACTIVE,
            PriceStatus.ARCHIVED,
        }:
            raise _conflict("Active prices cannot return to draft.")

    async def _publish(
        self, event_type: type[ProductPriceEvent], price: ProductPrice
    ) -> None:
        await self._events.publish(
            event_type(
                price_id=price.id,
                product_id=price.product_id,
                variant_id=price.variant_id,
                store_id=price.store_id,
                version=price.version,
            )
        )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Product price validation failed",
        detail="Product price fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_product_price", message=message)],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Product price not found",
        detail="The requested Product Price was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Product price conflict",
        detail=detail,
        status_code=409,
    )
