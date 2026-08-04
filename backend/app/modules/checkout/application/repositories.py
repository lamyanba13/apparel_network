from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.checkout.application.schemas import CheckoutFilter
from app.modules.checkout.domain import (
    CheckoutEvent,
    CheckoutItem,
    CheckoutSession,
    CheckoutStatus,
)


class CheckoutRepository(Protocol):
    async def exists_for_cart(self, cart_id: UUID) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> CheckoutSession: ...

    async def list_for_user(
        self, user_id: UUID, filters: CheckoutFilter
    ) -> tuple[Sequence[CheckoutSession], int]: ...

    async def get_for_user(
        self, checkout_id: UUID, user_id: UUID
    ) -> CheckoutSession | None: ...

    async def transition(
        self,
        checkout_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        status: CheckoutStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> CheckoutSession | None: ...

    async def archive(
        self,
        checkout_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> CheckoutSession | None: ...


class CheckoutItemRepository(Protocol):
    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[CheckoutItem]: ...

    async def list_for_checkout(self, checkout_id: UUID) -> Sequence[CheckoutItem]: ...

    async def validation_context(
        self, variant_id: UUID, store_id: UUID
    ) -> Mapping[str, object] | None: ...


class CheckoutOutboxRepository(Protocol):
    async def add(self, event: CheckoutEvent) -> None: ...
