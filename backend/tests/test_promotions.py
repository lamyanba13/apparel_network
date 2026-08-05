from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from prometheus_client import generate_latest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.api.schemas import CartItemResponse, CartResponse
from app.modules.checkout.api.schemas import CheckoutResponse, CheckoutSummaryResponse
from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.inventory.api.schemas import InventoryResponse
from app.modules.orders.api.schemas import OrderResponse, OrderSummaryResponse
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.promotions.api.schemas import (
    CouponResponse,
    PromotionDetailResponse,
    PromotionEvaluateResponse,
    PromotionListResponse,
    PromotionResponse,
)
from app.modules.promotions.domain import (
    CouponCreated,
    CouponRedeemed,
    PromotionActivated,
    PromotionApplied,
    PromotionArchived,
    PromotionCreated,
    PromotionRemoved,
    PromotionStatus,
    PromotionType,
    PromotionUpdated,
)
from app.modules.promotions.infrastructure.models import (
    PromotionCouponModel,
    PromotionCustomerUsageModel,
    PromotionModel,
    PromotionRedemptionModel,
    PromotionRuleModel,
)
from app.modules.stores.domain import Store
from tests.test_payment import _authorized_client, _second_identity

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


def _counter_value(name: str, labels: str = "") -> float:
    prefix = f"{name}{labels} "
    return next(
        float(line.removeprefix(prefix))
        for line in generate_latest().decode().splitlines()
        if line.startswith(prefix)
    )


async def _promotion(
    client: AsyncClient,
    headers: dict[str, str],
    store_id: UUID,
    name: str,
    promotion_type: str,
    **values: object,
) -> PromotionResponse:
    response = await client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "store_id": str(store_id),
            "name": name,
            "promotion_type": promotion_type,
            "status": "draft",
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return PromotionResponse.model_validate(response.json())


async def _activate(
    client: AsyncClient, headers: dict[str, str], promotion: PromotionResponse
) -> PromotionResponse:
    response = await client.post(
        f"/api/v1/promotions/{promotion.id}/activate",
        headers=headers,
        json={"version": promotion.version},
    )
    assert response.status_code == 200, response.text
    return PromotionResponse.model_validate(response.json())


def test_promotion_events_models_and_identifier_only_contracts() -> None:
    event_types = (
        PromotionCreated,
        PromotionUpdated,
        PromotionActivated,
        PromotionArchived,
        CouponCreated,
        CouponRedeemed,
        PromotionApplied,
        PromotionRemoved,
    )
    events = [
        event_type(
            promotion_id=UUID(int=1),
            store_id=UUID(int=2),
            coupon_id=UUID(int=3),
            customer_id=UUID(int=4),
            cart_id=UUID(int=5),
            checkout_session_id=UUID(int=6),
            version=1,
        )
        for event_type in event_types
    ]
    assert {event.event_name for event in events} == {
        "promotion.created",
        "promotion.updated",
        "promotion.activated",
        "promotion.archived",
        "coupon.created",
        "coupon.redeemed",
        "promotion.applied",
        "promotion.removed",
    }
    assert all(
        set(event.payload)
        == {
            "promotion_id",
            "store_id",
            "coupon_id",
            "customer_id",
            "cart_id",
            "checkout_session_id",
            "version",
            "timestamp",
        }
        for event in events
    )
    tables = (
        PromotionModel.__table__,
        PromotionRuleModel.__table__,
        PromotionCouponModel.__table__,
        PromotionRedemptionModel.__table__,
        PromotionCustomerUsageModel.__table__,
    )
    assert all(isinstance(table, Table) for table in tables)
    assert "uq_promotion_coupons_store_code" in {
        constraint.name
        for constraint in cast(Table, PromotionCouponModel.__table__).constraints
    }
    assert "uq_promotion_redemptions_checkout_promotion" in {
        constraint.name
        for constraint in cast(Table, PromotionRedemptionModel.__table__).constraints
    }


async def test_promotion_production_stack_resolution_snapshots_and_ownership(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _counter_value("fashion_network_promotion_created_total")
    activated_before = _counter_value("fashion_network_promotion_activated_total")
    applied_before = _counter_value("fashion_network_promotion_applied_total")
    redeemed_before = _counter_value("fashion_network_coupon_redeemed_total")

    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
    ) as (client, headers):
        inventory_response = await client.post(
            "/api/v1/inventory",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity_on_hand": 20,
                "quantity_reserved": 0,
            },
        )
        assert inventory_response.status_code == 201, inventory_response.text
        inventory = InventoryResponse.model_validate(inventory_response.json())

        price_response = await client.post(
            "/api/v1/prices",
            headers=headers,
            json={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "variant_id": str(product_variant.id),
                "currency_code": "INR",
                "base_price": "100.0000",
                "tax_class": "standard",
                "status": "draft",
            },
        )
        assert price_response.status_code == 201, price_response.text
        price = ProductPriceResponse.model_validate(price_response.json())
        price_activation = await client.patch(
            f"/api/v1/prices/{price.id}",
            headers=headers,
            json={"status": "active", "version": price.version},
        )
        assert price_activation.status_code == 200, price_activation.text

        cart_response = await client.post(
            "/api/v1/cart",
            headers=headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        assert cart_response.status_code == 201, cart_response.text
        cart = CartResponse.model_validate(cart_response.json())
        item_response = await client.post(
            f"/api/v1/cart/{cart.id}/items",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 6,
                "version": cart.version,
            },
        )
        assert item_response.status_code == 201, item_response.text
        CartItemResponse.model_validate(item_response.json())

        drafts = [
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Ten percent",
                "percentage",
                percentage="10.0000",
                priority=20,
                maximum_discount="75.0000",
                rules=[
                    {
                        "condition": "product",
                        "configuration": {"id": str(product.id)},
                    }
                ],
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Fixed five",
                "fixed_amount",
                fixed_amount="5.0000",
                currency="INR",
                priority=10,
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Buy two get one",
                "buy_x_get_y",
                buy_quantity=2,
                get_quantity=1,
                priority=8,
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Three item bundle",
                "bundle",
                bundle_quantity=3,
                bundle_price="250.0000",
                currency="INR",
                priority=7,
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Tier fifteen",
                "tier_discount",
                tiers=[{"minimum_quantity": 3, "percentage": "15.0000"}],
                priority=6,
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "Free shipping",
                "free_shipping",
                priority=5,
            ),
            await _promotion(
                client,
                headers,
                verified_store.id,
                "New customer coupon",
                "percentage",
                percentage="25.0000",
                public=False,
                first_purchase_only=True,
                usage_limit=5,
                per_customer_usage_limit=1,
                minimum_order_amount="500.0000",
                minimum_quantity=2,
                priority=30,
            ),
        ]
        active = [await _activate(client, headers, draft) for draft in drafts]
        coupon_response = await client.post(
            "/api/v1/coupons",
            headers=headers,
            json={
                "promotion_id": str(active[-1].id),
                "code": "welcome10",
                "usage_limit": 5,
                "per_customer_usage_limit": 1,
            },
        )
        assert coupon_response.status_code == 201, coupon_response.text
        coupon = CouponResponse.model_validate(coupon_response.json())
        duplicate_coupon = await client.post(
            "/api/v1/coupons",
            headers=headers,
            json={"promotion_id": str(active[-1].id), "code": "WELCOME10"},
        )
        expired_coupon = await client.post(
            "/api/v1/coupons",
            headers=headers,
            json={
                "promotion_id": str(active[-1].id),
                "code": "OLD2026",
                "effective_until": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            },
        )
        assert expired_coupon.status_code == 201, expired_coupon.text

        evaluation_response = await client.post(
            "/api/v1/promotions/evaluate",
            headers=headers,
            json={"cart_id": str(cart.id), "coupon_codes": ["WELCOME10"]},
        )
        assert evaluation_response.status_code == 200, evaluation_response.text
        evaluation = PromotionEvaluateResponse.model_validate(
            evaluation_response.json()
        )
        invalid_coupon = await client.post(
            "/api/v1/promotions/evaluate",
            headers=headers,
            json={"cart_id": str(cart.id), "coupon_codes": ["NOTREAL"]},
        )
        expired_evaluation = await client.post(
            "/api/v1/promotions/evaluate",
            headers=headers,
            json={"cart_id": str(cart.id), "coupon_codes": ["OLD2026"]},
        )
        cart_summary = await client.get(
            f"/api/v1/cart/{cart.id}/summary",
            headers=headers,
            params={"evaluate_promotions": True, "coupon_codes": "WELCOME10"},
        )

        checkout_response = await client.post(
            "/api/v1/checkout",
            headers=headers,
            json={"cart_id": str(cart.id), "coupon_codes": ["WELCOME10"]},
        )
        assert checkout_response.status_code == 201, checkout_response.text
        checkout = CheckoutResponse.model_validate(checkout_response.json())
        checkout_summary_response = await client.get(
            f"/api/v1/checkout/{checkout.id}/summary", headers=headers
        )
        assert checkout_summary_response.status_code == 200
        checkout_summary = CheckoutSummaryResponse.model_validate(
            checkout_summary_response.json()
        )
        usage_limited = await client.post(
            "/api/v1/promotions/evaluate",
            headers=headers,
            json={"cart_id": str(cart.id), "coupon_codes": ["WELCOME10"]},
        )

        stale_coupon = await client.patch(
            f"/api/v1/coupons/{coupon.id}",
            headers=headers,
            json={"active": False, "version": coupon.version + 1},
        )
        coupon_update = await client.patch(
            f"/api/v1/coupons/{coupon.id}",
            headers=headers,
            json={"code": "WELCOME10", "version": coupon.version},
        )
        assert coupon_update.status_code == 200, coupon_update.text

        confirm_checkout = await client.post(
            f"/api/v1/checkout/{checkout.id}/confirm",
            headers=headers,
            json={"version": checkout.version},
        )
        assert confirm_checkout.status_code == 200, confirm_checkout.text
        order_response = await client.post(
            "/api/v1/orders",
            headers=headers,
            json={"checkout_session_id": str(checkout.id)},
        )
        assert order_response.status_code == 201, order_response.text
        order = OrderResponse.model_validate(order_response.json())
        order_summary_response = await client.get(
            f"/api/v1/orders/{order.id}/summary", headers=headers
        )
        order_summary = OrderSummaryResponse.model_validate(
            order_summary_response.json()
        )
        confirm_order = await client.post(
            f"/api/v1/orders/{order.id}/confirm",
            headers=headers,
            json={"version": order.version},
        )
        assert confirm_order.status_code == 200, confirm_order.text

        exclusive_draft = await _promotion(
            client,
            headers,
            verified_store.id,
            "Exclusive winner",
            "percentage",
            percentage="20.0000",
            exclusive=True,
            stackable=False,
            priority=100,
        )
        exclusive = await _activate(client, headers, exclusive_draft)
        second_cart_response = await client.post(
            "/api/v1/cart",
            headers=headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        second_cart = CartResponse.model_validate(second_cart_response.json())
        second_item = await client.post(
            f"/api/v1/cart/{second_cart.id}/items",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 2,
                "version": second_cart.version,
            },
        )
        assert second_item.status_code == 201, second_item.text
        exclusive_evaluation_response = await client.post(
            "/api/v1/promotions/evaluate",
            headers=headers,
            json={
                "cart_id": str(second_cart.id),
                "coupon_codes": ["WELCOME10"],
            },
        )
        exclusive_evaluation = PromotionEvaluateResponse.model_validate(
            exclusive_evaluation_response.json()
        )

        listing = await client.get(
            "/api/v1/promotions",
            headers=headers,
            params={"store_id": str(verified_store.id)},
        )
        detail = await client.get(f"/api/v1/promotions/{active[0].id}", headers=headers)
        stale_update = await client.patch(
            f"/api/v1/promotions/{exclusive.id}",
            headers=headers,
            json={"name": "Stale name", "version": exclusive.version - 1},
        )
        update_response = await client.patch(
            f"/api/v1/promotions/{exclusive.id}",
            headers=headers,
            json={"name": "Exclusive updated", "version": exclusive.version},
        )
        updated = PromotionResponse.model_validate(update_response.json())
        archive_response = await client.post(
            f"/api/v1/promotions/{updated.id}/archive",
            headers=headers,
            json={"version": updated.version},
        )
        archived = PromotionResponse.model_validate(archive_response.json())
        reactivate = await client.post(
            f"/api/v1/promotions/{archived.id}/activate",
            headers=headers,
            json={"version": archived.version},
        )
        delete_response = await client.delete(
            f"/api/v1/promotions/{active[1].id}",
            headers=headers,
            params={"version": active[1].version},
        )
        hidden_after_delete = await client.get(
            f"/api/v1/promotions/{active[1].id}", headers=headers
        )

    async with _authorized_client(
        async_client, second_identity, db_session, role="customer"
    ) as (client, second_headers):
        cross_user = await client.post(
            "/api/v1/promotions/evaluate",
            headers=second_headers,
            json={"cart_id": str(second_cart.id)},
        )

    assert duplicate_coupon.status_code == 409
    assert evaluation.subtotal == 600
    assert {line.promotion_type for line in evaluation.applied_promotions} == set(
        PromotionType
    )
    assert evaluation.discount_total == 600
    assert evaluation.final_total == 0
    assert invalid_coupon.status_code == 200
    assert invalid_coupon.json()["rejected_promotions"][0]["coupon_code"] == "NOTREAL"
    assert expired_evaluation.status_code == 200
    assert any(
        value["reason"] == "Coupon has expired."
        for value in expired_evaluation.json()["rejected_promotions"]
    )
    assert cart_summary.status_code == 200
    assert checkout_summary.discount_total == evaluation.discount_total
    assert checkout_summary.final_total == evaluation.final_total
    assert len(checkout_summary.applied_promotions) == len(
        evaluation.applied_promotions
    )
    assert any(
        value["reason"] == "Per-customer usage limit was reached."
        for value in usage_limited.json()["rejected_promotions"]
    )
    assert stale_coupon.status_code == 409
    assert order_summary.discount_total == checkout_summary.discount_total
    assert order_summary.final_total == checkout_summary.final_total
    assert {
        (value.promotion_id, value.discount_amount)
        for value in order_summary.applied_promotions
    } == {
        (value.promotion_id, value.discount_amount)
        for value in checkout_summary.applied_promotions
    }
    assert len(exclusive_evaluation.applied_promotions) == 1
    assert exclusive_evaluation.applied_promotions[0].promotion_id == exclusive.id
    assert any(
        value.reason == "Promotion is limited to the first purchase."
        for value in exclusive_evaluation.rejected_promotions
    )
    page = PromotionListResponse.model_validate(listing.json())
    assert page.page.total == 8
    assert PromotionDetailResponse.model_validate(detail.json()).rules
    assert stale_update.status_code == 409
    assert archived.status is PromotionStatus.ARCHIVED
    assert reactivate.status_code == 409
    assert delete_response.status_code == 204
    assert hidden_after_delete.status_code == 404
    assert cross_user.status_code == 404
    assert inventory.quantity_on_hand == 20

    redemptions = (
        await db_session.scalars(
            select(PromotionRedemptionModel).where(
                PromotionRedemptionModel.checkout_session_id == checkout.id
            )
        )
    ).all()
    assert redemptions
    assert all(value.order_id == order.id for value in redemptions)
    assert all(value.snapshot and value.currency == "INR" for value in redemptions)
    usage_rows = (
        await db_session.scalars(
            select(PromotionCustomerUsageModel).where(
                PromotionCustomerUsageModel.customer_id
                == authenticated_identity.user.id
            )
        )
    ).all()
    assert usage_rows and all(value.usage_count == 1 for value in usage_rows)
    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "promotion"
            )
        )
    ).all()
    event_names = {value.event_name for value in outbox}
    assert {
        "promotion.created",
        "promotion.updated",
        "promotion.activated",
        "promotion.archived",
        "promotion.removed",
        "coupon.created",
        "coupon.redeemed",
        "promotion.applied",
    } <= event_names
    assert all(
        "discount_amount" not in value.payload and "coupon_code" not in value.payload
        for value in outbox
    )
    assert (
        _counter_value("fashion_network_promotion_created_total") == created_before + 8
    )
    assert (
        _counter_value("fashion_network_promotion_activated_total")
        == activated_before + 8
    )
    assert _counter_value(
        "fashion_network_promotion_applied_total"
    ) == applied_before + len(redemptions)
    assert (
        _counter_value("fashion_network_coupon_redeemed_total") == redeemed_before + 1
    )


def test_promotion_openapi_documents_routes_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/promotions", "promotion:create"),
        ("get", "/api/v1/promotions", "promotion:view"),
        ("get", "/api/v1/promotions/{promotion_id}", "promotion:view"),
        ("patch", "/api/v1/promotions/{promotion_id}", "promotion:update"),
        ("delete", "/api/v1/promotions/{promotion_id}", "promotion:update"),
        (
            "post",
            "/api/v1/promotions/{promotion_id}/activate",
            "promotion:activate",
        ),
        (
            "post",
            "/api/v1/promotions/{promotion_id}/archive",
            "promotion:archive",
        ),
        ("post", "/api/v1/coupons", "coupon:create"),
        ("get", "/api/v1/coupons", "coupon:view"),
        ("patch", "/api/v1/coupons/{coupon_id}", "coupon:update"),
        ("delete", "/api/v1/coupons/{coupon_id}", "coupon:update"),
        ("post", "/api/v1/promotions/evaluate", "coupon:redeem"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
