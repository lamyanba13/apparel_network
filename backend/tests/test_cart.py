from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from ipaddress import ip_address
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import generate_latest
from pydantic import SecretStr
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.cart.api.schemas import (
    CartItemResponse,
    CartListResponse,
    CartResponse,
    CartSummaryResponse,
)
from app.modules.cart.domain import CartCreated, CartStatus, PriceSnapshot, Quantity
from app.modules.cart.infrastructure.models import (
    ShoppingCartItemModel,
    ShoppingCartModel,
)
from app.modules.identity.application.authorization import (
    PermissionCache,
    PermissionService,
)
from app.modules.identity.application.schemas import (
    RefreshSessionCreate,
    RefreshSessionRecord,
)
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
    permissions = PermissionService(
        db_session,
        SqlAlchemyRoleRepository(db_session),
        SqlAlchemyPermissionRepository(db_session),
        SqlAlchemyIdentityGrantRepository(db_session),
        cast(PermissionCache, application.state.permission_cache),
        PermissionRegistry(),
        cast(EventPublisher, application.state.authentication_events),
    )
    if role is not None:
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
    refresh_session = await _fresh_session(
        db_session,
        identity.user.id,
        label=f"Cart test {role or 'existing-role'}",
    )
    token = cast(TokenService, application.state.token_service).create_access_token(
        user_id=identity.user.id, session_id=refresh_session.id
    )
    try:
        yield async_client, {"Authorization": f"Bearer {token}"}
    finally:
        application.dependency_overrides.pop(get_db, None)
        await request_session.close()


async def _second_identity(db_session: AsyncSession) -> AuthenticatedIdentity:
    user = await create_user(db_session, value=uuid7().int)
    now = datetime.now(UTC)
    session = await _fresh_session(db_session, user.id, label="Second integration")
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


async def _fresh_session(
    db_session: AsyncSession,
    user_id: UUID,
    *,
    label: str,
) -> RefreshSessionRecord:
    now = datetime.now(UTC)
    return await SqlAlchemyRefreshSessionRepository(db_session).add(
        RefreshSessionCreate(
            user_id=user_id,
            refresh_token_hash=SecretStr(uuid7().hex * 2),
            family_id=uuid7(),
            device_name=f"{label} device",
            display_name=f"{label} device",
            ip_address=ip_address("127.0.0.2"),
            user_agent="fashion-network-cart-test",
            last_activity_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
    )


def test_cart_value_objects_events_and_models() -> None:
    assert Quantity(1).value == 1
    snapshot = PriceSnapshot(
        price_id=UUID(int=1),
        amount=Decimal("0"),
        currency="inr",
        resolved_at=datetime.now(UTC),
    )
    assert snapshot.currency == "INR"
    event = CartCreated(
        cart_id=UUID(int=1),
        user_id=UUID(int=2),
        store_id=UUID(int=3),
        version=1,
    )
    assert set(event.payload) == {
        "cart_id",
        "user_id",
        "store_id",
        "item_id",
        "version",
        "timestamp",
    }
    cart_table = cast(Table, ShoppingCartModel.__table__)
    item_table = cast(Table, ShoppingCartItemModel.__table__)
    assert "uq_shopping_carts_active_user_store" in {
        index.name for index in cart_table.indexes
    }
    assert "uq_shopping_cart_items_cart_variant" in {
        index.name for index in item_table.indexes
    }
    assert "ck_shopping_cart_items_quantity_positive" in {
        constraint.name for constraint in item_table.constraints
    }


async def test_cart_production_stack_ownership_snapshots_inventory_outbox_and_metrics(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _counter_value("fashion_network_cart_created_total")
    added_before = _counter_value("fashion_network_cart_item_added_total")
    removed_before = _counter_value("fashion_network_cart_item_removed_total")
    abandoned_before = _counter_value("fashion_network_cart_abandoned_total")

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
        activation = await client.patch(
            f"/api/v1/prices/{draft_price.id}",
            headers=headers,
            json={"status": "active", "version": draft_price.version},
        )
        assert activation.status_code == 200, activation.text
        active_price = ProductPriceResponse.model_validate(activation.json())

        create_response = await client.post(
            "/api/v1/cart",
            headers=headers,
            json={"store_id": str(verified_store.id), "currency": "inr"},
        )
        assert create_response.status_code == 201, create_response.text
        cart = CartResponse.model_validate(create_response.json())
        duplicate_cart = await client.post(
            "/api/v1/cart",
            headers=headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        detail = await client.get(f"/api/v1/cart/{cart.id}", headers=headers)
        listing = await client.get("/api/v1/cart", headers=headers)

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
        item = CartItemResponse.model_validate(add_response.json())
        duplicate_item = await client.post(
            f"/api/v1/cart/{cart.id}/items",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 1,
                "version": 2,
            },
        )
        first_summary_response = await client.get(
            f"/api/v1/cart/{cart.id}/summary", headers=headers
        )
        first_summary = CartSummaryResponse.model_validate(
            first_summary_response.json()
        )

        price_update = await client.patch(
            f"/api/v1/prices/{active_price.id}",
            headers=headers,
            json={"base_price": "150.0000", "version": active_price.version},
        )
        assert price_update.status_code == 200, price_update.text
        unchanged_summary_response = await client.get(
            f"/api/v1/cart/{cart.id}/summary", headers=headers
        )
        unchanged_summary = CartSummaryResponse.model_validate(
            unchanged_summary_response.json()
        )

        unavailable = await client.patch(
            f"/api/v1/cart/{cart.id}/items/{item.id}",
            headers=headers,
            json={"quantity": 20, "version": item.version},
        )
        item_update_response = await client.patch(
            f"/api/v1/cart/{cart.id}/items/{item.id}",
            headers=headers,
            json={"quantity": 3, "version": item.version},
        )
        assert item_update_response.status_code == 200, item_update_response.text
        updated_item = CartItemResponse.model_validate(item_update_response.json())
        stale_update = await client.patch(
            f"/api/v1/cart/{cart.id}/items/{item.id}",
            headers=headers,
            json={"quantity": 4, "version": item.version},
        )
        updated_summary_response = await client.get(
            f"/api/v1/cart/{cart.id}/summary", headers=headers
        )
        updated_summary = CartSummaryResponse.model_validate(
            updated_summary_response.json()
        )

    async with _authorized_client(
        async_client,
        second_identity,
        db_session,
        role="customer",
    ) as (client, second_headers):
        hidden = await client.get(f"/api/v1/cart/{cart.id}", headers=second_headers)
        second_cart_response = await client.post(
            "/api/v1/cart",
            headers=second_headers,
            json={"store_id": str(verified_store.id), "currency": "INR"},
        )
        assert second_cart_response.status_code == 201, second_cart_response.text

    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
        role=None,
    ) as (client, headers):
        stale_remove = await client.delete(
            f"/api/v1/cart/{cart.id}/items/{item.id}",
            headers=headers,
            params={"version": item.version},
        )
        remove_response = await client.delete(
            f"/api/v1/cart/{cart.id}/items/{item.id}",
            headers=headers,
            params={"version": updated_item.version},
        )
        assert remove_response.status_code == 204, remove_response.text
        current_cart_response = await client.get(
            f"/api/v1/cart/{cart.id}", headers=headers
        )
        current_cart = CartResponse.model_validate(current_cart_response.json())
        readd_response = await client.post(
            f"/api/v1/cart/{cart.id}/items",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity": 1,
                "version": current_cart.version,
            },
        )
        assert readd_response.status_code == 201, readd_response.text
        final_cart_response = await client.get(
            f"/api/v1/cart/{cart.id}", headers=headers
        )
        final_cart = CartResponse.model_validate(final_cart_response.json())
        stale_delete = await client.delete(
            f"/api/v1/cart/{cart.id}",
            headers=headers,
            params={"version": 1},
        )
        delete_response = await client.delete(
            f"/api/v1/cart/{cart.id}",
            headers=headers,
            params={"version": final_cart.version},
        )
        hidden_after_delete = await client.get(
            f"/api/v1/cart/{cart.id}", headers=headers
        )
        inventory_after_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inventory_after = InventoryResponse.model_validate(
            inventory_after_response.json()
        )

    assert duplicate_cart.status_code == 409
    assert detail.status_code == 200
    page = CartListResponse.model_validate(listing.json())
    assert page.page.total == 1 and page.items[0].id == cart.id
    assert duplicate_item.status_code == 409
    assert item.price_snapshot_id == active_price.id
    assert item.unit_price == 125.5
    assert item.inventory_snapshot["quantity_available"] == 10
    assert first_summary.quantity == 2 and first_summary.subtotal == 251
    assert unchanged_summary.subtotal == first_summary.subtotal
    assert unavailable.status_code == 409
    assert updated_item.quantity == 3 and updated_item.unit_price == 150
    assert stale_update.status_code == 409
    assert updated_summary.quantity == 3 and updated_summary.subtotal == 450
    assert hidden.status_code == 404
    assert stale_remove.status_code == 409
    assert stale_delete.status_code == 409
    assert delete_response.status_code == 204
    assert hidden_after_delete.status_code == 404
    assert inventory_after.quantity_on_hand == 10
    assert inventory_after.quantity_reserved == 0
    assert inventory_after.quantity_available == 10

    persisted_cart = await db_session.get(ShoppingCartModel, cart.id)
    assert persisted_cart is not None
    assert persisted_cart.status is CartStatus.ABANDONED
    assert persisted_cart.deleted_at is not None
    persisted_items = (
        await db_session.scalars(
            select(ShoppingCartItemModel).where(
                ShoppingCartItemModel.cart_id == cart.id
            )
        )
    ).all()
    assert len(persisted_items) == 2
    assert all(model.deleted_at is not None for model in persisted_items)
    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "shopping_cart",
                EventOutboxModel.aggregate_id == cart.id,
            )
        )
    ).all()
    event_names = {event.event_name for event in outbox}
    assert {
        "cart.created",
        "cart.updated",
        "cart.item_added",
        "cart.item_updated",
        "cart.item_removed",
        "cart.deleted",
    } <= event_names
    assert all(
        set(event.payload)
        == {"cart_id", "user_id", "store_id", "item_id", "version", "timestamp"}
        for event in outbox
    )
    assert _counter_value("fashion_network_cart_created_total") == created_before + 2
    assert _counter_value("fashion_network_cart_item_added_total") == added_before + 2
    assert (
        _counter_value("fashion_network_cart_item_removed_total") == removed_before + 1
    )
    assert (
        _counter_value("fashion_network_cart_abandoned_total") == abandoned_before + 1
    )


def test_cart_openapi_documents_routes_and_permissions(application: FastAPI) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/cart", "cart:create"),
        ("get", "/api/v1/cart", "cart:view"),
        ("get", "/api/v1/cart/{cart_id}", "cart:view"),
        ("post", "/api/v1/cart/{cart_id}/items", "cart:update"),
        ("patch", "/api/v1/cart/{cart_id}/items/{item_id}", "cart:update"),
        ("delete", "/api/v1/cart/{cart_id}/items/{item_id}", "cart:update"),
        ("delete", "/api/v1/cart/{cart_id}", "cart:delete"),
        ("get", "/api/v1/cart/{cart_id}/summary", "cart:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
