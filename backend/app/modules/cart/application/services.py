from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.cart.application.repositories import (
    CartOutboxRepository,
    ShoppingCartItemRepository,
    ShoppingCartRepository,
)
from app.modules.cart.application.schemas import (
    CartCreate,
    CartFilter,
    CartItemCreate,
    CartItemUpdate,
    CartSummary,
)
from app.modules.cart.domain import (
    CartCheckedOut,
    CartCreated,
    CartDeleted,
    CartEvent,
    CartExpired,
    CartItemAdded,
    CartItemRemoved,
    CartItemUpdated,
    CartStatus,
    CartUpdated,
    PriceSnapshot,
    Quantity,
    ShoppingCart,
    ShoppingCartItem,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryStatus
from app.modules.pricing.application.price_list_schemas import ResolvePriceRequest
from app.modules.pricing.application.price_list_services import PricingResolver
from app.modules.pricing.domain.currencies import normalize_currency_code
from app.observability.metrics import (
    CART_ITEMS_ADDED,
    CART_ITEMS_REMOVED,
    CARTS_ABANDONED,
    CARTS_CHECKED_OUT,
    CARTS_CREATED,
    OUTBOX_WRITTEN,
)


class CartValidationService:
    @staticmethod
    def create(values: CartCreate, *, now: datetime) -> dict[str, object]:
        try:
            currency = normalize_currency_code(values.currency)
        except ValueError as error:
            raise _validation("currency", "Currency code is invalid.") from error
        expires_at = values.expires_at or now + timedelta(days=30)
        if expires_at.utcoffset() is None or expires_at <= now:
            raise _validation("expires_at", "Expiration must be a future timestamp.")
        return {
            "user_id": values.actor_id,
            "store_id": values.store_id,
            "status": CartStatus.ACTIVE,
            "currency": currency,
            "customer_group": values.customer_group,
            "expires_at": expires_at,
            "checked_out_at": None,
            "created_by_id": values.actor_id,
            "updated_by_id": values.actor_id,
        }

    @staticmethod
    def quantity(value: int) -> int:
        try:
            return Quantity(value).value
        except ValueError as error:
            raise _validation(
                "quantity", "Quantity must be a positive integer."
            ) from error

    @staticmethod
    def mutable(cart: ShoppingCart, *, now: datetime) -> None:
        if cart.status is not CartStatus.ACTIVE:
            raise _conflict("Only active Carts can be modified.")
        if cart.expires_at <= now:
            raise _conflict("The Cart has expired.")


class CartOutboxService:
    def __init__(self, repository: CartOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: CartEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class CartService:
    def __init__(
        self,
        carts: ShoppingCartRepository,
        items: ShoppingCartItemRepository,
        pricing: PricingResolver,
        inventory: InventoryService,
        outbox: CartOutboxService,
    ) -> None:
        self._carts = carts
        self._items = items
        self._pricing = pricing
        self._inventory = inventory
        self._outbox = outbox
        self._validation = CartValidationService()

    async def create(self, values: CartCreate) -> ShoppingCart:
        now = datetime.now(UTC)
        validated = self._validation.create(values, now=now)
        if not await self._carts.store_exists(values.store_id):
            raise _not_found("Store")
        if await self._carts.active_exists(values.actor_id, values.store_id):
            raise _conflict("This user already has an active Cart for the Store.")
        cart = await self._carts.add(validated)
        CARTS_CREATED.inc()
        await self._emit(CartCreated, cart)
        return cart

    async def list_owned(
        self, user_id: UUID, filters: CartFilter
    ) -> tuple[Sequence[ShoppingCart], int]:
        return await self._carts.list_for_user(user_id, filters)

    async def get_owned(self, cart_id: UUID, user_id: UUID) -> ShoppingCart:
        cart = await self._carts.get_for_user(cart_id, user_id)
        if cart is None:
            raise _not_found()
        return cart

    async def add_item(
        self, cart_id: UUID, user_id: UUID, values: CartItemCreate
    ) -> ShoppingCartItem:
        cart = await self.get_owned(cart_id, user_id)
        now = datetime.now(UTC)
        self._validation.mutable(cart, now=now)
        quantity = self._validation.quantity(values.quantity)
        if await self._items.get_by_variant(cart.id, values.variant_id) is not None:
            raise _conflict("The Variant is already present in this Cart.")
        product_id, price, inventory_snapshot = await self._snapshots(
            cart, values.variant_id, quantity, now
        )
        item = await self._items.add(
            {
                "cart_id": cart.id,
                "product_id": product_id,
                "variant_id": values.variant_id,
                "quantity": quantity,
                "price_snapshot_id": price.price_id,
                "unit_price": price.amount,
                "currency": price.currency,
                "inventory_snapshot": inventory_snapshot,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        updated_cart = await self._carts.touch(
            cart.id,
            user_id,
            expected_version=values.expected_cart_version,
            updated_by_id=values.actor_id,
        )
        if updated_cart is None:
            raise _conflict("The Cart was modified by another request.")
        CART_ITEMS_ADDED.inc()
        await self._emit(CartItemAdded, updated_cart, item.id)
        await self._emit(CartUpdated, updated_cart)
        return item

    async def update_item(
        self,
        cart_id: UUID,
        item_id: UUID,
        user_id: UUID,
        values: CartItemUpdate,
    ) -> ShoppingCartItem:
        cart = await self.get_owned(cart_id, user_id)
        now = datetime.now(UTC)
        self._validation.mutable(cart, now=now)
        current = await self._items.get_for_cart(item_id, cart.id)
        if current is None:
            raise _not_found("Cart Item")
        quantity = self._validation.quantity(values.quantity)
        _, price, inventory_snapshot = await self._snapshots(
            cart, current.variant_id, quantity, now
        )
        item = await self._items.update(
            item_id,
            cart.id,
            values={
                "quantity": quantity,
                "price_snapshot_id": price.price_id,
                "unit_price": price.amount,
                "currency": price.currency,
                "inventory_snapshot": inventory_snapshot,
                "updated_by_id": values.actor_id,
            },
            expected_version=values.expected_version,
        )
        if item is None:
            raise _conflict("The Cart Item was modified by another request.")
        updated_cart = await self._carts.touch(
            cart.id,
            user_id,
            expected_version=cart.version,
            updated_by_id=values.actor_id,
        )
        if updated_cart is None:
            raise _conflict("The Cart was modified by another request.")
        await self._emit(CartItemUpdated, updated_cart, item.id)
        await self._emit(CartUpdated, updated_cart)
        return item

    async def remove_item(
        self,
        cart_id: UUID,
        item_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
    ) -> None:
        cart = await self.get_owned(cart_id, user_id)
        now = datetime.now(UTC)
        self._validation.mutable(cart, now=now)
        if await self._items.get_for_cart(item_id, cart.id) is None:
            raise _not_found("Cart Item")
        item = await self._items.archive(
            item_id,
            cart.id,
            expected_version=expected_version,
            deleted_at=now,
            deleted_by_id=user_id,
        )
        if item is None:
            raise _conflict("The Cart Item was modified by another request.")
        updated_cart = await self._carts.touch(
            cart.id,
            user_id,
            expected_version=cart.version,
            updated_by_id=user_id,
        )
        if updated_cart is None:
            raise _conflict("The Cart was modified by another request.")
        CART_ITEMS_REMOVED.inc()
        await self._emit(CartItemRemoved, updated_cart, item.id)
        await self._emit(CartUpdated, updated_cart)

    async def delete_owned(
        self, cart_id: UUID, user_id: UUID, expected_version: int
    ) -> None:
        cart = await self.get_owned(cart_id, user_id)
        self._validation.mutable(cart, now=datetime.now(UTC))
        deleted_at = datetime.now(UTC)
        archived = await self._carts.archive(
            cart.id,
            user_id,
            expected_version=expected_version,
            deleted_at=deleted_at,
            deleted_by_id=user_id,
        )
        if archived is None:
            raise _conflict("The Cart was modified by another request.")
        await self._items.archive_for_cart(
            cart.id, deleted_at=deleted_at, deleted_by_id=user_id
        )
        CARTS_ABANDONED.inc()
        await self._emit(CartDeleted, archived)

    async def summary_owned(self, cart_id: UUID, user_id: UUID) -> CartSummary:
        cart = await self.get_owned(cart_id, user_id)
        items = await self._items.list_for_cart(cart.id)
        return CartSummary(
            cart_id=cart.id,
            items=items,
            subtotal=sum(
                (item.unit_price * item.quantity for item in items), Decimal("0")
            ),
            currency=cart.currency,
            quantity=sum(item.quantity for item in items),
        )

    async def checkout_owned(
        self, cart_id: UUID, user_id: UUID, expected_version: int
    ) -> ShoppingCart:
        cart = await self.get_owned(cart_id, user_id)
        now = datetime.now(UTC)
        self._validation.mutable(cart, now=now)
        if not await self._items.list_for_cart(cart.id):
            raise _conflict("An empty Cart cannot be checked out.")
        checked_out = await self._carts.transition(
            cart.id,
            user_id,
            expected_version=expected_version,
            status=CartStatus.CHECKED_OUT,
            transitioned_at=now,
            actor_id=user_id,
        )
        if checked_out is None:
            raise _conflict("The Cart was modified by another request.")
        CARTS_CHECKED_OUT.inc()
        await self._emit(CartCheckedOut, checked_out)
        return checked_out

    async def expire_owned(
        self, cart_id: UUID, user_id: UUID, expected_version: int
    ) -> ShoppingCart:
        cart = await self.get_owned(cart_id, user_id)
        now = datetime.now(UTC)
        if cart.status is not CartStatus.ACTIVE or cart.expires_at > now:
            raise _conflict("The Cart is not eligible for expiration.")
        expired = await self._carts.transition(
            cart.id,
            user_id,
            expected_version=expected_version,
            status=CartStatus.EXPIRED,
            transitioned_at=now,
            actor_id=user_id,
        )
        if expired is None:
            raise _conflict("The Cart was modified by another request.")
        await self._emit(CartExpired, expired)
        return expired

    async def _snapshots(
        self,
        cart: ShoppingCart,
        variant_id: UUID,
        quantity: int,
        now: datetime,
    ) -> tuple[UUID, PriceSnapshot, dict[str, object]]:
        context = await self._items.variant_context(variant_id, cart.store_id)
        if context is None:
            raise _not_found("Variant")
        product_id = context.get("product_id")
        owner_id = context.get("store_owner_id")
        inventory_id = context.get("inventory_id")
        if not all(
            isinstance(value, UUID) for value in (product_id, owner_id, inventory_id)
        ):
            raise _not_found("Variant")
        assert isinstance(product_id, UUID)
        assert isinstance(owner_id, UUID)
        assert isinstance(inventory_id, UUID)
        resolved = await self._pricing.resolve(
            ResolvePriceRequest(
                store_id=cart.store_id,
                product_id=product_id,
                variant_id=variant_id,
                currency=cart.currency,
                customer_group=cart.customer_group,
                timestamp=now,
                actor_id=owner_id,
            )
        )
        inventory = await self._inventory.get_owned(inventory_id, owner_id)
        if (
            inventory.status is not InventoryStatus.ACTIVE
            or inventory.quantity_available < quantity
        ):
            raise _conflict("The requested quantity is not currently available.")
        price = PriceSnapshot(
            price_id=resolved.price_id,
            amount=resolved.amount,
            currency=resolved.currency_code,
            resolved_at=resolved.resolved_at,
        )
        return (
            product_id,
            price,
            {
                "inventory_id": str(inventory.id),
                "inventory_version": inventory.version,
                "quantity_available": inventory.quantity_available,
                "validated_at": now.isoformat(),
            },
        )

    async def _emit(
        self,
        event_type: type[CartEvent],
        cart: ShoppingCart,
        item_id: UUID | None = None,
    ) -> None:
        await self._outbox.write(
            event_type(
                cart_id=cart.id,
                user_id=cart.user_id,
                store_id=cart.store_id,
                item_id=item_id,
                version=cart.version,
            )
        )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Cart validation failed",
        detail="Cart fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_cart_field", message=message)],
    )


def _not_found(subject: str = "Cart") -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{subject} not found",
        detail=f"The requested {subject} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Cart conflict",
        detail=detail,
        status_code=409,
    )
