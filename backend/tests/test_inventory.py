from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.catalogs.domain import Catalog
from app.modules.identity.application.authorization import (
    PermissionCache,
    PermissionService,
)
from app.modules.identity.application.services import (
    AuthenticatedIdentity,
    TokenService,
)
from app.modules.identity.domain.authorization import PermissionRegistry
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyIdentityGrantRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
)
from app.modules.inventory.api.schemas import InventoryListResponse, InventoryResponse
from app.modules.inventory.domain import InventoryStatus, TrackingPolicy
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from app.modules.products.domain import Product, ProductVariant
from app.modules.stores.domain import Store

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


class _EventLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.event_names: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.event_names.append(record.getMessage())


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
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    transport = cast(ASGITransport, async_client._transport)
    application = cast(FastAPI, transport.app)
    cache = cast(PermissionCache, application.state.permission_cache)
    authentication_events = cast(
        EventPublisher,
        application.state.authentication_events,
    )
    permissions = PermissionService(
        db_session,
        SqlAlchemyRoleRepository(db_session),
        SqlAlchemyPermissionRepository(db_session),
        SqlAlchemyIdentityGrantRepository(db_session),
        cache,
        PermissionRegistry(),
        authentication_events,
    )
    await permissions.assign_role(
        identity.user.id,
        "store_owner",
        assigned_by_id=identity.user.id,
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
    token_service = cast(TokenService, application.state.token_service)
    access_token = token_service.create_access_token(
        user_id=identity.user.id,
        session_id=identity.session.id,
    )
    try:
        yield async_client, {"Authorization": f"Bearer {access_token}"}
    finally:
        application.dependency_overrides.pop(get_db, None)
        await request_session.close()


async def _create_inventory(
    client: AsyncClient,
    headers: dict[str, str],
    variant: ProductVariant,
) -> tuple[Response, InventoryResponse]:
    response = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "variant_id": str(variant.id),
            "quantity_on_hand": 12,
            "quantity_reserved": 3,
            "status": "active",
            "tracking_policy": "track",
            "low_stock_threshold": 4,
        },
    )
    assert response.status_code == 201
    return response, InventoryResponse.model_validate(response.json())


async def test_create_inventory_through_production_stack(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    catalog: Catalog,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    event_logger = logging.getLogger("app.modules.stores.infrastructure.events")
    event_handler = _EventLogHandler()
    previous_level = event_logger.level
    event_logger.setLevel(logging.INFO)
    event_logger.addHandler(event_handler)
    created_before = _counter_value("fashion_network_inventory_created_total")

    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
    ) as (client, headers):
        try:
            response, payload = await _create_inventory(
                client,
                headers,
                product_variant,
            )
        finally:
            event_logger.removeHandler(event_handler)
            event_logger.setLevel(previous_level)

    assert response.headers["location"] == f"/api/v1/inventory/{payload.id}"
    assert payload.variant_id == product_variant.id
    assert payload.product_id == product.id
    assert payload.catalog_id == catalog.id
    assert payload.store_id == verified_store.id
    assert payload.sku_snapshot == product_variant.reference
    assert payload.quantity_on_hand == 12
    assert payload.quantity_reserved == 3
    assert payload.quantity_available == 9
    assert payload.status is InventoryStatus.ACTIVE
    assert payload.tracking_policy is TrackingPolicy.TRACK
    assert payload.low_stock_threshold == 4
    assert payload.version == 1
    assert payload.created_at == payload.updated_at

    persisted = await SqlAlchemyInventoryRepository(db_session).get_for_owner(
        payload.id,
        authenticated_identity.user.id,
    )
    assert persisted is not None
    assert persisted.variant_id == product_variant.id
    assert persisted.product_id == product.id
    assert persisted.catalog_id == catalog.id
    assert persisted.store_id == verified_store.id
    assert persisted.quantity_on_hand == 12
    assert persisted.quantity_reserved == 3
    assert persisted.quantity_available == 9
    assert persisted.version == 1
    assert persisted.created_by_id == authenticated_identity.user.id
    assert persisted.updated_by_id == authenticated_identity.user.id
    assert persisted.deleted_at is None
    assert persisted.created_at == payload.created_at
    assert persisted.updated_at == payload.updated_at
    assert "inventory.created" in event_handler.event_names
    assert _counter_value("fashion_network_inventory_created_total") == (
        created_before + 1
    )


async def test_get_inventory_detail_and_list_through_production_stack(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
    ) as (client, headers):
        _, created = await _create_inventory(client, headers, product_variant)

        detail_response = await client.get(
            f"/api/v1/inventory/{created.id}",
            headers=headers,
        )
        list_response = await client.get(
            "/api/v1/inventory",
            headers=headers,
        )

    assert detail_response.status_code == 200
    detail = InventoryResponse.model_validate(detail_response.json())
    assert detail == created

    assert list_response.status_code == 200
    inventory_page = InventoryListResponse.model_validate(list_response.json())
    assert inventory_page.items == [created]
    assert inventory_page.page.total == 1
    assert inventory_page.page.offset == 0
    assert inventory_page.page.limit == 25
    assert not inventory_page.page.has_more


async def test_update_inventory_enforces_optimistic_locking(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
    ) as (client, headers):
        _, created = await _create_inventory(client, headers, product_variant)
        updated_response = await client.patch(
            f"/api/v1/inventory/{created.id}",
            headers=headers,
            json={
                "quantity_on_hand": 15,
                "quantity_reserved": 4,
                "version": created.version,
            },
        )
        stale_response = await client.patch(
            f"/api/v1/inventory/{created.id}",
            headers=headers,
            json={"quantity_on_hand": 16, "version": created.version},
        )

    assert updated_response.status_code == 200
    updated = InventoryResponse.model_validate(updated_response.json())
    assert updated.quantity_on_hand == 15
    assert updated.quantity_reserved == 4
    assert updated.quantity_available == 11
    assert updated.version == 2

    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "conflict"

    persisted = await SqlAlchemyInventoryRepository(db_session).get_for_owner(
        created.id,
        authenticated_identity.user.id,
    )
    assert persisted is not None
    assert persisted.quantity_on_hand == 15
    assert persisted.quantity_reserved == 4
    assert persisted.quantity_available == 11
    assert persisted.version == 2
    assert persisted.updated_by_id == authenticated_identity.user.id


async def test_delete_inventory_soft_deletes_with_current_version(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
    ) as (client, headers):
        _, created = await _create_inventory(client, headers, product_variant)
        delete_response = await client.delete(
            f"/api/v1/inventory/{created.id}",
            params={"version": created.version},
            headers=headers,
        )

    assert delete_response.status_code == 204
    assert not delete_response.content
    model = await db_session.scalar(
        select(InventoryItemModel).where(InventoryItemModel.id == created.id)
    )
    assert model is not None
    assert model.deleted_at is not None
    assert model.status is InventoryStatus.DISCONTINUED
    assert model.version == 2
    assert model.updated_by_id == authenticated_identity.user.id


async def test_delete_inventory_rejects_stale_version_with_conflict(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
    ) as (client, headers):
        _, created = await _create_inventory(client, headers, product_variant)
        updated_response = await client.patch(
            f"/api/v1/inventory/{created.id}",
            headers=headers,
            json={"low_stock_threshold": 5, "version": created.version},
        )
        assert updated_response.status_code == 200

        stale_delete_response = await client.delete(
            f"/api/v1/inventory/{created.id}",
            params={"version": created.version},
            headers=headers,
        )
        detail_response = await client.get(
            f"/api/v1/inventory/{created.id}",
            headers=headers,
        )

    assert stale_delete_response.status_code == 409
    assert stale_delete_response.json()["code"] == "conflict"
    assert detail_response.status_code == 200
    current = InventoryResponse.model_validate(detail_response.json())
    assert current.version == 2
    assert current.low_stock_threshold == 5

    model = await db_session.scalar(
        select(InventoryItemModel).where(InventoryItemModel.id == created.id)
    )
    assert model is not None
    assert model.deleted_at is None
    assert model.status is InventoryStatus.ACTIVE
    assert model.version == 2
