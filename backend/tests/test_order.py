from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from ipaddress import ip_address
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import generate_latest
from pydantic import SecretStr
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.cart.api.schemas import CartResponse
from app.modules.checkout.api.schemas import CheckoutResponse, CheckoutSummaryResponse
from app.modules.identity.application.authorization import (
    PermissionCache,
    PermissionService,
)
from app.modules.identity.application.schemas import RefreshSessionCreate
from app.modules.identity.application.services import (
    AccessTokenClaims,
    AuthenticatedIdentity,
    TokenService,
)
from app.modules.identity.domain.authorization import PermissionRegistry
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyIdentityGrantRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyRoleRepository,
)
from app.modules.inventory.api.schemas import InventoryResponse
from app.modules.orders.api.schemas import (
    OrderListResponse,
    OrderResponse,
    OrderSummaryResponse,
)
from app.modules.orders.domain import (
    Money,
    OrderCreated,
    OrderNumber,
    OrderSnapshot,
    OrderStatus,
)
from app.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.stores.domain import Store
from tests.fixtures.identity import create_user

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


def _counter_value(name: str) -> float:
    prefix = f"{name} "
    return next(
        float(line.removeprefix(prefix))
        for line in generate_latest().decode().splitlines()
        if line.startswith(prefix)
    )


@asynccontextmanager
async def _authorized_client(
    async_client: AsyncClient,
    identity: AuthenticatedIdentity,
    db_session: AsyncSession,
    *,
    role: str | None,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    transport = cast(ASGITransport, async_client._transport)
    application = cast(FastAPI, transport.app)
    if role is not None:
        permissions = PermissionService(
            db_session,
            SqlAlchemyRoleRepository(db_session),
            SqlAlchemyPermissionRepository(db_session),
            SqlAlchemyIdentityGrantRepository(db_session),
            cast(PermissionCache, application.state.permission_cache),
            PermissionRegistry(),
            cast(EventPublisher, application.state.authentication_events),
        )
        await permissions.assign_role(
            identity.user.id, role, assigned_by_id=identity.user.id
        )
    connection = await db_session.connection()
    request_session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def request_database() -> AsyncIterator[AsyncSession]:
        yield request_session

    application.dependency_overrides[get_db] = request_database
    token = cast(TokenService, application.state.token_service).create_access_token(
        user_id=identity.user.id, session_id=identity.session.id
    )
    try:
        yield async_client, {"Authorization": f"Bearer {token}"}
    finally:
        application.dependency_overrides.pop(get_db, None)
        await request_session.close()


async def _second_identity(db_session: AsyncSession) -> AuthenticatedIdentity:
    user = await create_user(db_session, value=uuid7().int)
    now = datetime.now(UTC)
    session = await SqlAlchemyRefreshSessionRepository(db_session).add(
        RefreshSessionCreate(
            user_id=user.id,
            refresh_token_hash=SecretStr(uuid7().hex * 2),
            family_id=uuid7(),
            device_name="Order ownership device",
            display_name="Order ownership device",
            ip_address=ip_address("127.0.0.4"),
            user_agent="fashion-network-order-test",
            last_activity_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
    )
    return AuthenticatedIdentity(
        user,
        session,
        AccessTokenClaims(
            1,
            user.id,
            session.id,
            uuid7(),
            now,
            now,
            now + timedelta(minutes=15),
        ),
    )


def test_order_value_objects_events_and_models() -> None:
    now = datetime.now(UTC)
    number = OrderNumber.create(date(2026, 8, 4), 1)
    assert number.value == "ORD-20260804-000001"
    with pytest.raises(ValueError):
        OrderNumber("invalid")
    snapshot = OrderSnapshot(
        price_id=UUID(int=1),
        money=Money(Decimal("10.5000"), "inr"),
        inventory_id=UUID(int=2),
        inventory_version=3,
        snapshot_timestamp=now,
    )
    assert snapshot.money.currency == "INR"
    event = OrderCreated(
        order_id=UUID(int=1),
        checkout_session_id=UUID(int=2),
        customer_id=UUID(int=3),
        store_id=UUID(int=4),
        version=1,
    )
    assert set(event.payload) == {
        "order_id",
        "checkout_session_id",
        "customer_id",
        "store_id",
        "version",
        "timestamp",
    }
    order_table = cast(Table, OrderModel.__table__)
    item_table = cast(Table, OrderItemModel.__table__)
    assert {"uq_orders_order_number", "uq_orders_checkout_session"} <= {
        constraint.name for constraint in order_table.constraints
    }
    assert "uq_order_items_order_variant" in {
        constraint.name for constraint in item_table.constraints
    }
    assert "ck_orders_lifecycle_timestamps" in {
        constraint.name for constraint in order_table.constraints
    }


async def test_order_production_stack_checkout_snapshots_numbering_and_lifecycle(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _counter_value("fashion_network_order_created_total")
    confirmed_before = _counter_value("fashion_network_order_confirmed_total")
    cancelled_before = _counter_value("fashion_network_order_cancelled_total")

    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
        role="store_owner",
    ) as (client, headers):
        inventory_response = await client.post(
            "/api/v1/inventory",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity_on_hand": 10,
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
                "base_price": "125.5000",
                "tax_class": "standard",
                "status": "draft",
            },
        )
        assert price_response.status_code == 201, price_response.text
        draft_price = ProductPriceResponse.model_validate(price_response.json())
        activation_response = await client.patch(
            f"/api/v1/prices/{draft_price.id}",
            headers=headers,
            json={"status": "active", "version": draft_price.version},
        )
        assert activation_response.status_code == 200, activation_response.text
        active_price = ProductPriceResponse.model_validate(activation_response.json())

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
                "quantity": 2,
                "version": cart.version,
            },
        )
        assert item_response.status_code == 201, item_response.text
        checkout_response = await client.post(
            "/api/v1/checkout",
            headers=headers,
            json={"cart_id": str(cart.id)},
        )
        assert checkout_response.status_code == 201, checkout_response.text
        checkout = CheckoutResponse.model_validate(checkout_response.json())
        unconfirmed_checkout_order = await client.post(
            "/api/v1/orders",
            headers=headers,
            json={"checkout_session_id": str(checkout.id)},
        )
        checkout_confirm_response = await client.post(
            f"/api/v1/checkout/{checkout.id}/confirm",
            headers=headers,
            json={"version": checkout.version},
        )
        assert (
            checkout_confirm_response.status_code == 200
        ), checkout_confirm_response.text
        checkout_summary_response = await client.get(
            f"/api/v1/checkout/{checkout.id}/summary", headers=headers
        )
        checkout_summary = CheckoutSummaryResponse.model_validate(
            checkout_summary_response.json()
        )

        later_price_response = await client.patch(
            f"/api/v1/prices/{active_price.id}",
            headers=headers,
            json={"base_price": "150.0000", "version": active_price.version},
        )
        assert later_price_response.status_code == 200, later_price_response.text
        later_inventory_response = await client.patch(
            f"/api/v1/inventory/{inventory.id}",
            headers=headers,
            json={"quantity_on_hand": 8, "version": inventory.version},
        )
        assert (
            later_inventory_response.status_code == 200
        ), later_inventory_response.text
        later_inventory = InventoryResponse.model_validate(
            later_inventory_response.json()
        )

        create_response = await client.post(
            "/api/v1/orders",
            headers=headers,
            json={"checkout_session_id": str(checkout.id)},
        )
        assert create_response.status_code == 201, create_response.text
        order = OrderResponse.model_validate(create_response.json())
        duplicate_order = await client.post(
            "/api/v1/orders",
            headers=headers,
            json={"checkout_session_id": str(checkout.id)},
        )
        detail_response = await client.get(
            f"/api/v1/orders/{order.id}", headers=headers
        )
        list_response = await client.get("/api/v1/orders", headers=headers)
        summary_response = await client.get(
            f"/api/v1/orders/{order.id}/summary", headers=headers
        )
        summary = OrderSummaryResponse.model_validate(summary_response.json())
        pending_cancel = await client.delete(
            f"/api/v1/orders/{order.id}",
            headers=headers,
            params={"version": order.version},
        )
        stale_confirm = await client.post(
            f"/api/v1/orders/{order.id}/confirm",
            headers=headers,
            json={"version": order.version + 1},
        )
        confirm_response = await client.post(
            f"/api/v1/orders/{order.id}/confirm",
            headers=headers,
            json={"version": order.version},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        confirmed_order = OrderResponse.model_validate(confirm_response.json())
        repeated_confirm = await client.post(
            f"/api/v1/orders/{order.id}/confirm",
            headers=headers,
            json={"version": confirmed_order.version},
        )

    async with _authorized_client(
        async_client,
        second_identity,
        db_session,
        role="customer",
    ) as (client, second_headers):
        hidden = await client.get(f"/api/v1/orders/{order.id}", headers=second_headers)
        second_cart_response = await client.post(
            "/api/v1/cart",
            headers=second_headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        assert second_cart_response.status_code == 201, second_cart_response.text
        second_cart = CartResponse.model_validate(second_cart_response.json())
        second_item_response = await client.post(
            f"/api/v1/cart/{second_cart.id}/items",
            headers=second_headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 1,
                "version": second_cart.version,
            },
        )
        assert second_item_response.status_code == 201, second_item_response.text
        second_checkout_response = await client.post(
            "/api/v1/checkout",
            headers=second_headers,
            json={"cart_id": str(second_cart.id)},
        )
        assert (
            second_checkout_response.status_code == 201
        ), second_checkout_response.text
        second_checkout = CheckoutResponse.model_validate(
            second_checkout_response.json()
        )
        second_checkout_confirm = await client.post(
            f"/api/v1/checkout/{second_checkout.id}/confirm",
            headers=second_headers,
            json={"version": second_checkout.version},
        )
        assert second_checkout_confirm.status_code == 200, second_checkout_confirm.text
        second_order_response = await client.post(
            "/api/v1/orders",
            headers=second_headers,
            json={"checkout_session_id": str(second_checkout.id)},
        )
        assert second_order_response.status_code == 201, second_order_response.text
        second_order = OrderResponse.model_validate(second_order_response.json())
        second_order_confirm = await client.post(
            f"/api/v1/orders/{second_order.id}/confirm",
            headers=second_headers,
            json={"version": second_order.version},
        )
        assert second_order_confirm.status_code == 200, second_order_confirm.text
        second_confirmed = OrderResponse.model_validate(second_order_confirm.json())
        stale_cancel = await client.delete(
            f"/api/v1/orders/{second_order.id}",
            headers=second_headers,
            params={"version": second_confirmed.version + 1},
        )
        cancel_response = await client.delete(
            f"/api/v1/orders/{second_order.id}",
            headers=second_headers,
            params={"version": second_confirmed.version},
        )
        hidden_cancelled = await client.get(
            f"/api/v1/orders/{second_order.id}", headers=second_headers
        )
    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
        role=None,
    ) as (client, headers):
        inventory_after_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        assert (
            inventory_after_response.status_code == 200
        ), inventory_after_response.text
        inventory_after = InventoryResponse.model_validate(
            inventory_after_response.json()
        )

    assert unconfirmed_checkout_order.status_code == 409
    assert duplicate_order.status_code == 409
    assert detail_response.status_code == 200
    page = OrderListResponse.model_validate(list_response.json())
    assert page.page.total == 1 and page.items[0].id == order.id
    assert re.fullmatch(r"ORD-[0-9]{8}-[0-9]{6}", order.order_number)
    assert int(second_order.order_number[-6:]) == int(order.order_number[-6:]) + 1
    assert order.checkout_session_id == checkout.id
    assert order.cart_id == cart.id
    assert order.store_id == verified_store.id
    assert order.customer_id == authenticated_identity.user.id
    assert order.status is OrderStatus.PENDING
    assert order.subtotal == 251
    assert summary.quantity == 2 and summary.subtotal == 251
    assert len(summary.items) == 1
    order_item = summary.items[0]
    checkout_item = checkout_summary.items[0]
    assert order_item.product_id == product.id
    assert order_item.variant_id == product_variant.id
    assert order_item.price_id == checkout_item.price_id
    assert order_item.unit_price == checkout_item.unit_price == 125.5
    assert order_item.inventory_id == checkout_item.inventory_id == inventory.id
    assert order_item.inventory_version == checkout_item.inventory_version
    assert order_item.inventory_version != later_inventory.version
    assert order_item.snapshot_timestamp == max(
        checkout_item.price_snapshot_time, checkout_item.inventory_snapshot_time
    )
    assert pending_cancel.status_code == 409
    assert stale_confirm.status_code == 409
    assert confirmed_order.status is OrderStatus.CONFIRMED
    assert confirmed_order.confirmed_at is not None
    assert repeated_confirm.status_code == 409
    assert hidden.status_code == 404
    assert stale_cancel.status_code == 409
    assert cancel_response.status_code == 204
    assert hidden_cancelled.status_code == 404
    assert inventory_after.quantity_on_hand == 8
    assert inventory_after.quantity_reserved == 0
    assert inventory_after.quantity_available == 8

    persisted = await db_session.get(OrderModel, order.id)
    assert persisted is not None
    assert persisted.status is OrderStatus.CONFIRMED
    persisted_items = (
        await db_session.scalars(
            select(OrderItemModel).where(OrderItemModel.order_id == order.id)
        )
    ).all()
    assert len(persisted_items) == 1
    assert persisted_items[0].unit_price == 125.5
    assert persisted_items[0].version == 1
    cancelled = await db_session.get(OrderModel, second_order.id)
    assert cancelled is not None
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.confirmed_at is not None
    assert cancelled.cancelled_at is not None
    assert cancelled.deleted_at is not None

    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "order",
                EventOutboxModel.aggregate_id.in_([order.id, second_order.id]),
            )
        )
    ).all()
    event_names = {event.event_name for event in outbox}
    assert {"order.created", "order.confirmed", "order.cancelled"} <= event_names
    assert all(
        set(event.payload)
        == {
            "order_id",
            "checkout_session_id",
            "customer_id",
            "store_id",
            "version",
            "timestamp",
        }
        for event in outbox
    )
    assert _counter_value("fashion_network_order_created_total") == created_before + 2
    assert (
        _counter_value("fashion_network_order_confirmed_total") == confirmed_before + 2
    )
    assert (
        _counter_value("fashion_network_order_cancelled_total") == cancelled_before + 1
    )


def test_order_openapi_documents_routes_and_permissions(application: FastAPI) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/orders", "order:create"),
        ("get", "/api/v1/orders", "order:view"),
        ("get", "/api/v1/orders/{order_id}", "order:view"),
        ("post", "/api/v1/orders/{order_id}/confirm", "order:confirm"),
        ("delete", "/api/v1/orders/{order_id}", "order:update"),
        ("get", "/api/v1/orders/{order_id}/summary", "order:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
