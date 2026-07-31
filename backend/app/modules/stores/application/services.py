from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from uuid6 import uuid7

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.application.schemas import StoreCreate, StoreUpdate
from app.modules.stores.domain import (
    Store,
    StoreAddress,
    StoreClosed,
    StoreContact,
    StoreCreated,
    StoreStatus,
    StoreSubmitted,
    StoreSuspended,
    StoreUpdated,
    StoreVerified,
    VerificationStatus,
)
from app.observability.metrics import (
    STORES_ACTIVE,
    STORES_CREATED,
    STORES_VERIFIED,
)

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{6,30}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_POSTAL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{2,19}$")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class StoreValidationService:
    """Validate and normalize Store aggregate values."""

    def validate_create(self, values: StoreCreate) -> StoreCreate:
        return StoreCreate(
            owner_id=values.owner_id,
            name=self.name(values.name),
            description=self.optional_text(
                values.description,
                field="description",
                maximum=2000,
            ),
            contact=self.contact(values.contact),
            address=self.address(values.address),
            logo_url=self.optional_url(values.logo_url, field="logo_url"),
            banner_url=self.optional_url(values.banner_url, field="banner_url"),
        )

    def validate_changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "name",
            "description",
            "phone",
            "email",
            "website",
            "address",
            "city",
            "district",
            "state",
            "country",
            "postal_code",
            "latitude",
            "longitude",
            "logo_url",
            "banner_url",
        }
        if not values or not set(values) <= allowed:
            raise _validation_error("body", "At least one supported field is required.")
        normalized = dict(values)
        if "name" in normalized:
            normalized["name"] = self.name(_required_string(normalized["name"], "name"))
        if "description" in normalized:
            normalized["description"] = self.optional_text(
                _optional_string(normalized["description"], "description"),
                field="description",
                maximum=2000,
            )
        for field, maximum in (
            ("address", 300),
            ("city", 100),
            ("district", 100),
            ("state", 100),
            ("country", 100),
            ("postal_code", 20),
        ):
            if field in normalized:
                normalized[field] = self.required_text(
                    _required_string(normalized[field], field),
                    field=field,
                    maximum=maximum,
                )
        if "phone" in normalized:
            normalized["phone"] = self.phone(
                _required_string(normalized["phone"], "phone")
            )
        if "email" in normalized:
            normalized["email"] = self.email(
                _required_string(normalized["email"], "email")
            )
        for field in ("website", "logo_url", "banner_url"):
            if field in normalized:
                normalized[field] = self.optional_url(
                    _optional_string(normalized[field], field),
                    field=field,
                )
        self._validate_coordinates(normalized)
        if "postal_code" in normalized and not _POSTAL_PATTERN.fullmatch(
            str(normalized["postal_code"])
        ):
            raise _validation_error("postal_code", "Postal code format is invalid.")
        return normalized

    def name(self, value: str) -> str:
        return self.required_text(value, field="name", minimum=2, maximum=150)

    def contact(self, value: StoreContact) -> StoreContact:
        return StoreContact(
            phone=self.phone(value.phone),
            email=self.email(value.email),
            website=self.optional_url(value.website, field="website"),
        )

    def address(self, value: StoreAddress) -> StoreAddress:
        address = StoreAddress(
            address=self.required_text(value.address, field="address", maximum=300),
            city=self.required_text(value.city, field="city", maximum=100),
            district=self.required_text(value.district, field="district", maximum=100),
            state=self.required_text(value.state, field="state", maximum=100),
            country=self.required_text(value.country, field="country", maximum=100),
            postal_code=self.required_text(
                value.postal_code, field="postal_code", maximum=20
            ),
            latitude=value.latitude,
            longitude=value.longitude,
        )
        if not _POSTAL_PATTERN.fullmatch(address.postal_code):
            raise _validation_error("postal_code", "Postal code format is invalid.")
        self._coordinates(address.latitude, address.longitude)
        return address

    def phone(self, value: str) -> str:
        normalized = value.strip()
        if not _PHONE_PATTERN.fullmatch(normalized):
            raise _validation_error("phone", "Phone number format is invalid.")
        return normalized

    def email(self, value: str) -> str:
        normalized = value.strip().casefold()
        if len(normalized) > 320 or not _EMAIL_PATTERN.fullmatch(normalized):
            raise _validation_error("email", "Email address format is invalid.")
        return normalized

    def required_text(
        self,
        value: str,
        *,
        field: str,
        minimum: int = 1,
        maximum: int,
    ) -> str:
        normalized = " ".join(value.split())
        if not minimum <= len(normalized) <= maximum:
            raise _validation_error(
                field,
                f"{field.replace('_', ' ').title()} must contain "
                f"{minimum} to {maximum} characters.",
            )
        return normalized

    def optional_text(
        self,
        value: str | None,
        *,
        field: str,
        maximum: int,
    ) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if len(normalized) > maximum:
            raise _validation_error(
                field,
                f"{field.replace('_', ' ').title()} cannot exceed "
                f"{maximum} characters.",
            )
        return normalized

    def optional_url(self, value: str | None, *, field: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        parsed = urlsplit(normalized)
        if (
            len(normalized) > 2048
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
        ):
            raise _validation_error(field, "URL must use HTTP or HTTPS.")
        return normalized

    def _validate_coordinates(self, values: Mapping[str, object]) -> None:
        if "latitude" not in values and "longitude" not in values:
            return
        latitude = values.get("latitude")
        longitude = values.get("longitude")
        if latitude is not None and not isinstance(latitude, Decimal):
            raise _validation_error("latitude", "Latitude must be a decimal.")
        if longitude is not None and not isinstance(longitude, Decimal):
            raise _validation_error("longitude", "Longitude must be a decimal.")
        self._coordinates(latitude, longitude)

    def _coordinates(
        self,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> None:
        if (latitude is None) != (longitude is None):
            raise _validation_error(
                "latitude",
                "Latitude and longitude must be provided together.",
            )
        if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
            raise _validation_error("latitude", "Latitude must be between -90 and 90.")
        if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
            raise _validation_error(
                "longitude",
                "Longitude must be between -180 and 180.",
            )


class StoreSlugService:
    """Generate stable, URL-safe, collision-resistant store slugs."""

    async def create(
        self,
        name: str,
        exists: Callable[[str], Awaitable[bool]],
    ) -> str:
        ascii_name = (
            unicodedata.normalize("NFKD", name)
            .encode("ascii", "ignore")
            .decode()
            .lower()
        )
        base = _SLUG_PATTERN.sub("-", ascii_name).strip("-") or "store"
        base = base[:150].rstrip("-")
        if not await exists(base):
            return base
        return f"{base}-{uuid7().hex[:12]}"


class StoreService:
    def __init__(
        self,
        repository: StoreRepository,
        events: EventPublisher,
        validation: StoreValidationService,
        slugs: StoreSlugService,
    ) -> None:
        self._repository = repository
        self._events = events
        self._validation = validation
        self._slugs = slugs

    async def create(self, values: StoreCreate) -> Store:
        validated = self._validation.validate_create(values)
        slug = await self._slugs.create(
            validated.name,
            self._repository.slug_exists,
        )
        store = await self._repository.add(
            owner_id=validated.owner_id,
            name=validated.name,
            slug=slug,
            description=validated.description,
            contact=validated.contact,
            address=validated.address,
            logo_url=validated.logo_url,
            banner_url=validated.banner_url,
        )
        STORES_CREATED.inc()
        await self._events.publish(
            StoreCreated(
                store_id=store.id,
                owner_id=store.owner_id,
                correlation_id=_correlation_id(),
            )
        )
        await self._snapshot_metrics()
        return store

    async def list_owned(
        self,
        owner_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Store], int]:
        return await self._repository.list_for_owner(
            owner_id,
            offset=offset,
            limit=limit,
        )

    async def get_owned(self, store_id: UUID, owner_id: UUID) -> Store:
        store = await self._repository.get_for_owner(store_id, owner_id)
        if store is None:
            raise _not_found()
        return store

    async def update_owned(
        self,
        store_id: UUID,
        owner_id: UUID,
        values: StoreUpdate,
    ) -> Store:
        changes = self._validation.validate_changes(values.values)
        store = await self._repository.update(
            store_id,
            owner_id,
            values=changes,
            expected_version=values.expected_version,
        )
        if store is None:
            existing = await self._repository.get_for_owner(store_id, owner_id)
            if existing is None:
                raise _not_found()
            raise _conflict("The store was modified by another request.")
        await self._events.publish(
            StoreUpdated(
                store_id=store.id,
                owner_id=store.owner_id,
                correlation_id=_correlation_id(),
            )
        )
        return store

    async def delete_owned(self, store_id: UUID, owner_id: UUID) -> None:
        store = await self._repository.close_for_owner(
            store_id,
            owner_id,
            deleted_at=datetime.now(UTC),
        )
        if store is None:
            raise _not_found()
        await self._events.publish(
            StoreClosed(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                correlation_id=_correlation_id(),
            )
        )
        await self._snapshot_metrics()

    async def _snapshot_metrics(self) -> None:
        active, verified = await self._repository.count_active_and_verified()
        STORES_ACTIVE.set(active)
        STORES_VERIFIED.set(verified)


class StoreLifecycleService:
    """Enforce Store state transitions independently from transport."""

    def __init__(
        self,
        repository: StoreRepository,
        events: EventPublisher,
    ) -> None:
        self._repository = repository
        self._events = events

    async def submit(self, store_id: UUID) -> Store:
        store = await self._transition(
            store_id,
            from_statuses=frozenset({StoreStatus.DRAFT}),
            status=StoreStatus.PENDING_REVIEW,
            verification_status=VerificationStatus.PENDING,
        )
        await self._events.publish(
            StoreSubmitted(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                verification_status=store.verification_status,
                correlation_id=_correlation_id(),
            )
        )
        return store

    async def verify(self, store_id: UUID) -> Store:
        store = await self._transition(
            store_id,
            from_statuses=frozenset({StoreStatus.PENDING_REVIEW}),
            status=StoreStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
        )
        await self._events.publish(
            StoreVerified(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                verification_status=store.verification_status,
                correlation_id=_correlation_id(),
            )
        )
        return store

    async def suspend(self, store_id: UUID) -> Store:
        store = await self._transition(
            store_id,
            from_statuses=frozenset({StoreStatus.PENDING_REVIEW, StoreStatus.ACTIVE}),
            status=StoreStatus.SUSPENDED,
        )
        await self._events.publish(
            StoreSuspended(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                correlation_id=_correlation_id(),
            )
        )
        return store

    async def close(self, store_id: UUID) -> Store:
        store = await self._transition(
            store_id,
            from_statuses=frozenset(
                {
                    StoreStatus.DRAFT,
                    StoreStatus.PENDING_REVIEW,
                    StoreStatus.ACTIVE,
                    StoreStatus.SUSPENDED,
                }
            ),
            status=StoreStatus.CLOSED,
            deleted_at=datetime.now(UTC),
        )
        await self._events.publish(
            StoreClosed(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                correlation_id=_correlation_id(),
            )
        )
        return store

    async def _transition(
        self,
        store_id: UUID,
        *,
        from_statuses: frozenset[StoreStatus],
        status: StoreStatus,
        verification_status: VerificationStatus | None = None,
        deleted_at: datetime | None = None,
    ) -> Store:
        existing = await self._repository.get_by_id(store_id)
        if existing is None:
            raise _not_found()
        store = await self._repository.transition(
            store_id,
            from_statuses=from_statuses,
            status=status,
            verification_status=verification_status,
            deleted_at=deleted_at,
        )
        if store is None:
            raise _conflict(
                f"Store cannot transition from {existing.status.value} "
                f"to {status.value}."
            )
        active, verified = await self._repository.count_active_and_verified()
        STORES_ACTIVE.set(active)
        STORES_VERIFIED.set(verified)
        return store


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _validation_error(field, f"{field} cannot be null.")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise _validation_error(field, f"{field} must be a string or null.")


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store not found",
        detail="The requested store was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Store conflict",
        detail=detail,
        status_code=409,
    )


def _validation_error(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store validation failed",
        detail="One or more store fields are invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_field",
                message=message,
            )
        ],
    )


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
