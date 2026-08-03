from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.pricing.application.price_list_schemas import PriceListFilter
from app.modules.pricing.domain import (
    CustomerGroup,
    PriceAssignment,
    PriceList,
    ResolvedPrice,
)


class PriceListRepository(Protocol):
    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool: ...

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool: ...

    async def default_exists(
        self,
        store_id: UUID,
        currency_code: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool: ...

    async def priority_conflict_exists(
        self,
        *,
        store_id: UUID,
        currency_code: str,
        customer_group: CustomerGroup,
        priority: int,
        effective_from: datetime | None,
        effective_until: datetime | None,
        exclude_id: UUID | None = None,
    ) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> PriceList: ...

    async def list_for_owner(
        self, owner_id: UUID, filters: PriceListFilter
    ) -> tuple[Sequence[PriceList], int]: ...

    async def get_for_owner(
        self, price_list_id: UUID, owner_id: UUID
    ) -> PriceList | None: ...

    async def update(
        self,
        price_list_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> PriceList | None: ...

    async def archive(
        self,
        price_list_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> PriceList | None: ...


class AssignmentRepository(Protocol):
    async def price_context(
        self, price_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None: ...

    async def add(
        self, price_list_id: UUID, price_id: UUID, actor_id: UUID
    ) -> PriceAssignment | None: ...

    async def remove(
        self, price_list_id: UUID, price_id: UUID
    ) -> PriceAssignment | None: ...


class ResolverRepository(Protocol):
    async def context_owned(
        self,
        store_id: UUID,
        product_id: UUID,
        variant_id: UUID | None,
        owner_id: UUID,
    ) -> bool: ...

    async def resolve(
        self,
        *,
        store_id: UUID,
        product_id: UUID,
        variant_id: UUID | None,
        currency_code: str,
        customer_group: CustomerGroup,
        timestamp: datetime,
    ) -> ResolvedPrice | None: ...
