from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.cart.application.schemas import CartFilter
from app.modules.cart.domain import (
    CartEvent,
    CartStatus,
    ShoppingCart,
    ShoppingCartItem,
)


class ShoppingCartRepository(Protocol):
    async def store_exists(self, store_id: UUID) -> bool: ...

    async def active_exists(self, user_id: UUID, store_id: UUID) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> ShoppingCart: ...

    async def list_for_user(
        self, user_id: UUID, filters: CartFilter
    ) -> tuple[Sequence[ShoppingCart], int]: ...

    async def get_for_user(
        self, cart_id: UUID, user_id: UUID
    ) -> ShoppingCart | None: ...

    async def touch(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        updated_by_id: UUID,
    ) -> ShoppingCart | None: ...

    async def transition(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        status: CartStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> ShoppingCart | None: ...

    async def archive(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ShoppingCart | None: ...


class ShoppingCartItemRepository(Protocol):
    async def variant_context(
        self, variant_id: UUID, store_id: UUID
    ) -> Mapping[str, object] | None: ...

    async def add(self, values: Mapping[str, object]) -> ShoppingCartItem: ...

    async def list_for_cart(self, cart_id: UUID) -> Sequence[ShoppingCartItem]: ...

    async def get_for_cart(
        self, item_id: UUID, cart_id: UUID
    ) -> ShoppingCartItem | None: ...

    async def archive_for_cart(
        self, cart_id: UUID, *, deleted_at: datetime, deleted_by_id: UUID
    ) -> None: ...

    async def get_by_variant(
        self, cart_id: UUID, variant_id: UUID
    ) -> ShoppingCartItem | None: ...

    async def update(
        self,
        item_id: UUID,
        cart_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ShoppingCartItem | None: ...

    async def archive(
        self,
        item_id: UUID,
        cart_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ShoppingCartItem | None: ...


class CartOutboxRepository(Protocol):
    async def add(self, event: CartEvent) -> None: ...
