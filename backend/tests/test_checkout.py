from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
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
from app.modules.cart.api.schemas import CartItemResponse, CartResponse
from app.modules.cart.domain import CartStatus
from app.modules.cart.infrastructure.models import ShoppingCartModel
from app.modules.checkout.api.schemas import (
    CheckoutListResponse,
    CheckoutResponse,
    CheckoutSummaryResponse,
)
from app.modules.checkout.domain import (
    CheckoutCreated,
    CheckoutSnapshot,
    CheckoutStatus,
    Money,
)
from app.modules.checkout.infrastructure.models import (
    CheckoutSessionItemModel,
    CheckoutSessionModel,
)
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
            device_name="Checkout ownership device",
            display_name="Checkout ownership device",
            ip_address=ip_address("127.0.0.3"),
            user_agent="fashion-network-checkout-test",
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


def test_checkout_value_objects_events_and_models() -> None:
    now = datetime.now(UTC)
    money = Money(Decimal("10.5000"), "inr")
    snapshot = CheckoutSnapshot(
        price_id=UUID(int=1),
        money=money,
        inventory_id=UUID(int=2),
        inventory_version=3,
        price_snapshot_time=now,
        inventory_snapshot_time=now,
    )
    assert snapshot.money.currency == "INR"
    with pytest.raises(ValueError):
        Money(Decimal("-1"), "INR")
    event = CheckoutCreated(
        checkout_id=UUID(int=1),
        cart_id=UUID(int=2),
        user_id=UUID(int=3),
        store_id=UUID(int=4),
        version=1,
    )
    assert set(event.payload) == {
        "checkout_id",
        "cart_id",
        "user_id",
        "store_id",
        "version",
        "timestamp",
    }
    session_table = cast(Table, CheckoutSessionModel.__table__)
    item_table = cast(Table, CheckoutSessionItemModel.__table__)
    assert "uq_checkout_sessions_cart" in {
        constraint.name for constraint in session_table.constraints
    }
    assert "uq_checkout_session_items_session_variant" in {
        constraint.name for constraint in item_table.constraints
    }
    assert "ck_checkout_session_items_quantity_positive" in {
        constraint.name for constraint in item_table.constraints
    }


async def test_checkout_production_stack_revalidation_snapshots_ownership_and_lifecycle(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    third_identity = await _second_identity(db_session)
    created_before = _counter_value("fashion_network_checkout_created_total")
    confirmed_before = _counter_value("fashion_network_checkout_confirmed_total")
    cancelled_before = _counter_value("fashion_network_checkout_cancelled_total")
    expired_before = _counter_value("fashion_network_checkout_expired_total")

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
        empty_checkout = await client.post(
            "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
        )
        add_response = await client.post(
            f"/api/v1/cart/{cart.id}/items",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 2,
                "version": cart.version,
            },
        )
        assert add_response.status_code == 201, add_response.text
        cart_item = CartItemResponse.model_validate(add_response.json())

        low_inventory_response = await client.patch(
            f"/api/v1/inventory/{inventory.id}",
            headers=headers,
            json={"quantity_on_hand": 1, "version": inventory.version},
        )
        assert low_inventory_response.status_code == 200, low_inventory_response.text
        low_inventory = InventoryResponse.model_validate(low_inventory_response.json())
        unavailable_checkout = await client.post(
            "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
        )
        restore_inventory_response = await client.patch(
            f"/api/v1/inventory/{inventory.id}",
            headers=headers,
            json={"quantity_on_hand": 10, "version": low_inventory.version},
        )
        assert (
            restore_inventory_response.status_code == 200
        ), restore_inventory_response.text
        restored_inventory = InventoryResponse.model_validate(
            restore_inventory_response.json()
        )

        price_update_response = await client.patch(
            f"/api/v1/prices/{active_price.id}",
            headers=headers,
            json={"base_price": "150.0000", "version": active_price.version},
        )
        assert price_update_response.status_code == 200, price_update_response.text
        checkout_price = ProductPriceResponse.model_validate(
            price_update_response.json()
        )
        create_response = await client.post(
            "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
        )
        assert create_response.status_code == 201, create_response.text
        checkout = CheckoutResponse.model_validate(create_response.json())
        duplicate_checkout = await client.post(
            "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
        )
        detail_response = await client.get(
            f"/api/v1/checkout/{checkout.id}", headers=headers
        )
        list_response = await client.get("/api/v1/checkout", headers=headers)
        first_summary_response = await client.get(
            f"/api/v1/checkout/{checkout.id}/summary", headers=headers
        )
        first_summary = CheckoutSummaryResponse.model_validate(
            first_summary_response.json()
        )

        later_price_response = await client.patch(
            f"/api/v1/prices/{checkout_price.id}",
            headers=headers,
            json={"base_price": "175.0000", "version": checkout_price.version},
        )
        assert later_price_response.status_code == 200, later_price_response.text
        unchanged_summary_response = await client.get(
            f"/api/v1/checkout/{checkout.id}/summary", headers=headers
        )
        unchanged_summary = CheckoutSummaryResponse.model_validate(
            unchanged_summary_response.json()
        )
        stale_confirm = await client.post(
            f"/api/v1/checkout/{checkout.id}/confirm",
            headers=headers,
            json={"version": checkout.version + 1},
        )

    async with _authorized_client(
        async_client,
        second_identity,
        db_session,
        role="customer",
    ) as (client, second_headers):
        hidden = await client.get(
            f"/api/v1/checkout/{checkout.id}", headers=second_headers
        )
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
        stale_cancel = await client.delete(
            f"/api/v1/checkout/{second_checkout.id}",
            headers=second_headers,
            params={"version": second_checkout.version + 1},
        )
        cancel_response = await client.delete(
            f"/api/v1/checkout/{second_checkout.id}",
            headers=second_headers,
            params={"version": second_checkout.version},
        )
        hidden_cancelled = await client.get(
            f"/api/v1/checkout/{second_checkout.id}", headers=second_headers
        )

    async with _authorized_client(
        async_client,
        third_identity,
        db_session,
        role="customer",
    ) as (client, third_headers):
        third_cart_response = await client.post(
            "/api/v1/cart",
            headers=third_headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        assert third_cart_response.status_code == 201, third_cart_response.text
        third_cart = CartResponse.model_validate(third_cart_response.json())
        third_item_response = await client.post(
            f"/api/v1/cart/{third_cart.id}/items",
            headers=third_headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 1,
                "version": third_cart.version,
            },
        )
        assert third_item_response.status_code == 201, third_item_response.text
        third_checkout_response = await client.post(
            "/api/v1/checkout",
            headers=third_headers,
            json={
                "cart_id": str(third_cart.id),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=2)).isoformat(),
            },
        )
        assert third_checkout_response.status_code == 201, third_checkout_response.text
        third_checkout = CheckoutResponse.model_validate(third_checkout_response.json())
        await asyncio.sleep(2.1)
        expired_response = await client.get(
            f"/api/v1/checkout/{third_checkout.id}", headers=third_headers
        )
        assert expired_response.status_code == 200, expired_response.text
        expired_checkout = CheckoutResponse.model_validate(expired_response.json())

    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
        role=None,
    ) as (client, headers):
        confirm_response = await client.post(
            f"/api/v1/checkout/{checkout.id}/confirm",
            headers=headers,
            json={"version": checkout.version},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        confirmed = CheckoutResponse.model_validate(confirm_response.json())
        repeated_confirm = await client.post(
            f"/api/v1/checkout/{checkout.id}/confirm",
            headers=headers,
            json={"version": confirmed.version},
        )
        cart_after_response = await client.get(
            f"/api/v1/cart/{cart.id}", headers=headers
        )
        cart_after = CartResponse.model_validate(cart_after_response.json())
        inventory_after_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inventory_after = InventoryResponse.model_validate(
            inventory_after_response.json()
        )

    assert empty_checkout.status_code == 409
    assert unavailable_checkout.status_code == 409
    assert duplicate_checkout.status_code == 409
    assert detail_response.status_code == 200
    page = CheckoutListResponse.model_validate(list_response.json())
    assert page.page.total == 1 and page.items[0].id == checkout.id
    assert checkout.subtotal == 300
    assert first_summary.quantity == 2
    assert first_summary.subtotal == 300
    assert len(first_summary.items) == 1
    checkout_item = first_summary.items[0]
    assert checkout_item.variant_id == product_variant.id
    assert checkout_item.product_id == product.id
    assert checkout_item.price_id == checkout_price.id
    assert checkout_item.unit_price == 150
    assert checkout_item.inventory_id == inventory.id
    assert checkout_item.inventory_version == restored_inventory.version
    assert checkout_item.price_snapshot_time.tzinfo is not None
    assert checkout_item.inventory_snapshot_time.tzinfo is not None
    assert cart_item.unit_price == 125.5
    assert unchanged_summary == first_summary
    assert stale_confirm.status_code == 409
    assert hidden.status_code == 404
    assert stale_cancel.status_code == 409
    assert cancel_response.status_code == 204
    assert hidden_cancelled.status_code == 404
    assert expired_checkout.status is CheckoutStatus.EXPIRED
    assert confirmed.status is CheckoutStatus.CONFIRMED
    assert confirmed.completed_at is not None
    assert repeated_confirm.status_code == 409
    assert cart_after.status is CartStatus.CHECKED_OUT
    assert inventory_after.quantity_on_hand == 10
    assert inventory_after.quantity_reserved == 0
    assert inventory_after.quantity_available == 10

    persisted = await db_session.get(CheckoutSessionModel, checkout.id)
    assert persisted is not None
    assert persisted.status is CheckoutStatus.CONFIRMED
    persisted_items = (
        await db_session.scalars(
            select(CheckoutSessionItemModel).where(
                CheckoutSessionItemModel.checkout_session_id == checkout.id
            )
        )
    ).all()
    assert len(persisted_items) == 1
    assert persisted_items[0].unit_price == 150
    assert persisted_items[0].version == 1
    cancelled = await db_session.get(CheckoutSessionModel, second_checkout.id)
    assert cancelled is not None
    assert cancelled.status is CheckoutStatus.CANCELLED
    assert cancelled.deleted_at is not None
    persisted_cart = await db_session.get(ShoppingCartModel, cart.id)
    assert persisted_cart is not None
    assert persisted_cart.status is CartStatus.CHECKED_OUT

    checkout_outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "checkout_session",
                EventOutboxModel.aggregate_id.in_(
                    [checkout.id, second_checkout.id, third_checkout.id]
                ),
            )
        )
    ).all()
    event_names = {event.event_name for event in checkout_outbox}
    assert {
        "checkout.created",
        "checkout.confirmed",
        "checkout.cancelled",
        "checkout.expired",
    } <= event_names
    assert all(
        set(event.payload)
        == {
            "checkout_id",
            "cart_id",
            "user_id",
            "store_id",
            "version",
            "timestamp",
        }
        for event in checkout_outbox
    )
    assert (
        _counter_value("fashion_network_checkout_created_total") == created_before + 3
    )
    assert (
        _counter_value("fashion_network_checkout_confirmed_total")
        == confirmed_before + 1
    )
    assert (
        _counter_value("fashion_network_checkout_cancelled_total")
        == cancelled_before + 1
    )
    assert (
        _counter_value("fashion_network_checkout_expired_total") == expired_before + 1
    )


def test_checkout_openapi_documents_routes_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/checkout", "checkout:create"),
        ("get", "/api/v1/checkout", "checkout:view"),
        ("get", "/api/v1/checkout/{checkout_id}", "checkout:view"),
        ("post", "/api/v1/checkout/{checkout_id}/confirm", "checkout:confirm"),
        ("delete", "/api/v1/checkout/{checkout_id}", "checkout:update"),
        ("get", "/api/v1/checkout/{checkout_id}/summary", "checkout:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
