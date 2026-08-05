from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.cart.application.services import CartService
from app.modules.cart.domain import CartStatus, ShoppingCart, ShoppingCartItem
from app.modules.checkout.application.repositories import (
    CheckoutItemRepository,
    CheckoutOutboxRepository,
    CheckoutRepository,
)
from app.modules.checkout.application.schemas import (
    CheckoutConfirm,
    CheckoutCreate,
    CheckoutFilter,
    CheckoutSummary,
)
from app.modules.checkout.domain import (
    CheckoutCancelled,
    CheckoutConfirmed,
    CheckoutCreated,
    CheckoutEvent,
    CheckoutExpired,
    CheckoutSession,
    CheckoutSnapshot,
    CheckoutStatus,
    Money,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryStatus
from app.modules.pricing.application.price_list_schemas import ResolvePriceRequest
from app.modules.pricing.application.price_list_services import PricingResolver
from app.modules.promotions.application.services import PromotionEvaluationService
from app.modules.promotions.domain import PromotionRedemption
from app.observability.metrics import (
    CHECKOUTS_CANCELLED,
    CHECKOUTS_CONFIRMED,
    CHECKOUTS_CREATED,
    CHECKOUTS_EXPIRED,
    OUTBOX_WRITTEN,
)


@dataclass(frozen=True, slots=True)
class _PreparedItem:
    source: ShoppingCartItem
    snapshot: CheckoutSnapshot


class CheckoutValidationService:
    @staticmethod
    def expires_at(value: datetime | None, *, now: datetime) -> datetime:
        expires_at = value or now + timedelta(minutes=15)
        if expires_at.utcoffset() is None or expires_at <= now:
            raise _validation("expires_at", "Expiration must be a future timestamp.")
        return expires_at

    @staticmethod
    def cart(cart: ShoppingCart, *, now: datetime) -> None:
        if cart.status is not CartStatus.ACTIVE:
            raise _conflict("Only an active Cart can enter Checkout.")
        if cart.expires_at <= now:
            raise _conflict("The Cart has expired.")

    @staticmethod
    def items(values: Sequence[ShoppingCartItem]) -> None:
        if not values:
            raise _conflict("An empty Cart cannot enter Checkout.")

    @staticmethod
    def active(value: CheckoutSession) -> None:
        if value.status is not CheckoutStatus.ACTIVE:
            raise _conflict("Only an active Checkout Session can be modified.")


class CheckoutOutboxService:
    def __init__(self, repository: CheckoutOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: CheckoutEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class CheckoutService:
    def __init__(
        self,
        checkouts: CheckoutRepository,
        items: CheckoutItemRepository,
        carts: CartService,
        pricing: PricingResolver,
        inventory: InventoryService,
        promotions: PromotionEvaluationService,
        outbox: CheckoutOutboxService,
    ) -> None:
        self._checkouts = checkouts
        self._items = items
        self._carts = carts
        self._pricing = pricing
        self._inventory = inventory
        self._promotions = promotions
        self._outbox = outbox
        self._validation = CheckoutValidationService()

    async def create(self, values: CheckoutCreate) -> CheckoutSession:
        now = datetime.now(UTC)
        cart = await self._carts.get_owned(values.cart_id, values.actor_id)
        self._validation.cart(cart, now=now)
        if await self._checkouts.exists_for_cart(cart.id):
            raise _conflict("This Cart already has a Checkout Session.")
        cart_summary = await self._carts.summary_owned(cart.id, values.actor_id)
        self._validation.items(cart_summary.items)
        prepared = [
            await self._prepare_item(cart, item, now) for item in cart_summary.items
        ]
        subtotal = sum(
            (item.snapshot.money.amount * item.source.quantity for item in prepared),
            Decimal("0"),
        )
        checkout = await self._checkouts.add(
            {
                "cart_id": cart.id,
                "user_id": cart.user_id,
                "store_id": cart.store_id,
                "status": CheckoutStatus.ACTIVE,
                "currency": cart.currency,
                "subtotal": subtotal,
                "expires_at": self._validation.expires_at(values.expires_at, now=now),
                "completed_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._items.add_many(
            [self._item_values(checkout.id, values.actor_id, item) for item in prepared]
        )
        await self._promotions.freeze_checkout(
            checkout.id,
            cart.id,
            values.actor_id,
            values.coupon_codes,
        )
        CHECKOUTS_CREATED.inc()
        await self._emit(CheckoutCreated, checkout)
        return checkout

    async def list_owned(
        self, user_id: UUID, filters: CheckoutFilter
    ) -> tuple[Sequence[CheckoutSession], int]:
        checkouts, total = await self._checkouts.list_for_user(user_id, filters)
        return [await self._expire_if_needed(value) for value in checkouts], total

    async def get_owned(self, checkout_id: UUID, user_id: UUID) -> CheckoutSession:
        checkout = await self._get_owned(checkout_id, user_id)
        return await self._expire_if_needed(checkout)

    async def confirm_owned(
        self,
        checkout_id: UUID,
        user_id: UUID,
        values: CheckoutConfirm,
    ) -> CheckoutSession:
        checkout = await self._get_owned(checkout_id, user_id)
        self._validation.active(checkout)
        now = datetime.now(UTC)
        if checkout.expires_at <= now:
            raise _conflict("The Checkout Session has expired.")
        confirmed = await self._checkouts.transition(
            checkout.id,
            user_id,
            expected_version=values.expected_version,
            status=CheckoutStatus.CONFIRMED,
            transitioned_at=now,
            actor_id=values.actor_id,
        )
        if confirmed is None:
            raise _conflict("The Checkout Session was modified by another request.")
        cart = await self._carts.get_owned(checkout.cart_id, user_id)
        await self._carts.checkout_owned(cart.id, user_id, cart.version)
        CHECKOUTS_CONFIRMED.inc()
        await self._emit(CheckoutConfirmed, confirmed)
        return confirmed

    async def cancel_owned(
        self, checkout_id: UUID, user_id: UUID, expected_version: int
    ) -> None:
        checkout = await self._get_owned(checkout_id, user_id)
        self._validation.active(checkout)
        now = datetime.now(UTC)
        if checkout.expires_at <= now:
            raise _conflict("The Checkout Session has expired.")
        cancelled = await self._checkouts.archive(
            checkout.id,
            user_id,
            expected_version=expected_version,
            deleted_at=now,
            deleted_by_id=user_id,
        )
        if cancelled is None:
            raise _conflict("The Checkout Session was modified by another request.")
        CHECKOUTS_CANCELLED.inc()
        await self._emit(CheckoutCancelled, cancelled)

    async def summary_owned(self, checkout_id: UUID, user_id: UUID) -> CheckoutSummary:
        checkout = await self.get_owned(checkout_id, user_id)
        items = await self._items.list_for_checkout(checkout.id)
        promotions = await self._promotions.checkout_snapshots(checkout.id, user_id)
        discount_total = sum(
            (promotion.discount_amount for promotion in promotions), Decimal("0")
        )
        return CheckoutSummary(
            checkout_session_id=checkout.id,
            items=items,
            subtotal=checkout.subtotal,
            discount_total=discount_total,
            final_total=checkout.subtotal - discount_total,
            currency=checkout.currency,
            quantity=sum(item.quantity for item in items),
            applied_promotions=promotions,
        )

    async def inherit_promotions_to_order(
        self,
        checkout_id: UUID,
        order_id: UUID,
        user_id: UUID,
    ) -> Sequence[PromotionRedemption]:
        await self._get_owned(checkout_id, user_id)
        return await self._promotions.link_order(checkout_id, order_id, user_id)

    async def order_promotion_snapshots_owned(
        self, order_id: UUID, user_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._promotions.order_snapshots(order_id, user_id)

    async def _get_owned(self, checkout_id: UUID, user_id: UUID) -> CheckoutSession:
        checkout = await self._checkouts.get_for_user(checkout_id, user_id)
        if checkout is None:
            raise _not_found()
        return checkout

    async def _expire_if_needed(self, checkout: CheckoutSession) -> CheckoutSession:
        now = datetime.now(UTC)
        if checkout.status is not CheckoutStatus.ACTIVE or checkout.expires_at > now:
            return checkout
        expired = await self._checkouts.transition(
            checkout.id,
            checkout.user_id,
            expected_version=checkout.version,
            status=CheckoutStatus.EXPIRED,
            transitioned_at=now,
            actor_id=checkout.user_id,
        )
        if expired is None:
            refreshed = await self._get_owned(checkout.id, checkout.user_id)
            return refreshed
        CHECKOUTS_EXPIRED.inc()
        await self._emit(CheckoutExpired, expired)
        return expired

    async def _prepare_item(
        self,
        cart: ShoppingCart,
        item: ShoppingCartItem,
        now: datetime,
    ) -> _PreparedItem:
        context = await self._items.validation_context(item.variant_id, cart.store_id)
        if context is None:
            raise _not_found("Variant")
        product_id = context.get("product_id")
        owner_id = context.get("store_owner_id")
        inventory_id = context.get("inventory_id")
        if not all(
            isinstance(value, UUID) for value in (product_id, owner_id, inventory_id)
        ):
            raise _not_found("Variant")
        if product_id != item.product_id:
            raise _conflict("The Cart Item no longer matches its Product.")
        assert isinstance(owner_id, UUID)
        assert isinstance(inventory_id, UUID)
        resolved = await self._pricing.resolve(
            ResolvePriceRequest(
                store_id=cart.store_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                currency=cart.currency,
                customer_group=cart.customer_group,
                timestamp=now,
                actor_id=owner_id,
            )
        )
        inventory = await self._inventory.get_owned(inventory_id, owner_id)
        if (
            inventory.status is not InventoryStatus.ACTIVE
            or inventory.quantity_available < item.quantity
        ):
            raise _conflict("A Checkout Item is no longer available.")
        return _PreparedItem(
            source=item,
            snapshot=CheckoutSnapshot(
                price_id=resolved.price_id,
                money=Money(resolved.amount, resolved.currency_code),
                inventory_id=inventory.id,
                inventory_version=inventory.version,
                price_snapshot_time=resolved.resolved_at,
                inventory_snapshot_time=now,
            ),
        )

    @staticmethod
    def _item_values(
        checkout_id: UUID, actor_id: UUID, prepared: _PreparedItem
    ) -> Mapping[str, object]:
        snapshot = prepared.snapshot
        return {
            "checkout_session_id": checkout_id,
            "product_id": prepared.source.product_id,
            "variant_id": prepared.source.variant_id,
            "quantity": prepared.source.quantity,
            "price_id": snapshot.price_id,
            "unit_price": snapshot.money.amount,
            "currency": snapshot.money.currency,
            "inventory_id": snapshot.inventory_id,
            "inventory_version": snapshot.inventory_version,
            "price_snapshot_time": snapshot.price_snapshot_time,
            "inventory_snapshot_time": snapshot.inventory_snapshot_time,
            "created_by_id": actor_id,
            "updated_by_id": actor_id,
        }

    async def _emit(
        self, event_type: type[CheckoutEvent], checkout: CheckoutSession
    ) -> None:
        await self._outbox.write(
            event_type(
                checkout_id=checkout.id,
                cart_id=checkout.cart_id,
                user_id=checkout.user_id,
                store_id=checkout.store_id,
                version=checkout.version,
            )
        )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Checkout validation failed",
        detail="Checkout fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_checkout_field", message=message)
        ],
    )


def _not_found(subject: str = "Checkout Session") -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{subject} not found",
        detail=f"The requested {subject} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Checkout conflict",
        detail=detail,
        status_code=409,
    )
