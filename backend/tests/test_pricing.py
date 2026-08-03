from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from prometheus_client import generate_latest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.database.session import get_db
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
from app.modules.pricing.api.schemas import (
    ProductPriceListResponse,
    ProductPriceResponse,
)
from app.modules.pricing.application.schemas import ProductPriceCreate
from app.modules.pricing.application.services import ProductPriceValidationService
from app.modules.pricing.domain import (
    Money,
    PriceStatus,
    ProductPriceCreated,
)
from app.modules.pricing.infrastructure.models import ProductPriceModel
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
    token = cast(TokenService, application.state.token_service).create_access_token(
        user_id=identity.user.id,
        session_id=identity.session.id,
    )
    try:
        yield async_client, {"Authorization": f"Bearer {token}"}
    finally:
        application.dependency_overrides.pop(get_db, None)
        await request_session.close()


def _price_payload(
    store: Store,
    product: Product,
    variant: ProductVariant,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "store_id": str(store.id),
        "product_id": str(product.id),
        "variant_id": str(variant.id),
        "currency_code": "INR",
        "base_price": "1999.0000",
        "sale_price": "1499.0000",
        "compare_at_price": "2499.0000",
        "cost_price": "900.0000",
        "tax_class": "standard",
        "status": "draft",
    }
    payload.update(overrides)
    return payload


async def _create_price(
    client: AsyncClient,
    headers: dict[str, str],
    store: Store,
    product: Product,
    variant: ProductVariant,
    **overrides: object,
) -> tuple[Response, ProductPriceResponse]:
    response = await client.post(
        "/api/v1/prices",
        headers=headers,
        json=_price_payload(store, product, variant, **overrides),
    )
    assert response.status_code == 201
    return response, ProductPriceResponse.model_validate(response.json())


def test_money_currency_and_price_validation() -> None:
    assert Money(Decimal("10.2500"), "inr").currency_code == "INR"
    with pytest.raises(ValueError):
        Money(Decimal("-0.01"), "INR")
    with pytest.raises(ValueError):
        Money(Decimal("1.00001"), "INR")
    with pytest.raises(ValueError):
        Money(Decimal("1"), "US1")

    validator = ProductPriceValidationService()
    now = datetime.now(UTC)
    with pytest.raises(AppError):
        validator.validate_create(
            ProductPriceCreate(
                store_id=UUID(int=1),
                product_id=UUID(int=2),
                variant_id=UUID(int=3),
                currency_code="INR",
                base_price=Decimal("10"),
                sale_price=Decimal("11"),
                compare_at_price=None,
                cost_price=None,
                tax_class="standard",
                status=PriceStatus.DRAFT,
                effective_from=now,
                effective_until=now + timedelta(days=1),
                actor_id=UUID(int=4),
            )
        )


def test_product_price_events_are_identifier_only() -> None:
    event = ProductPriceCreated(
        price_id=UUID(int=1),
        product_id=UUID(int=2),
        variant_id=UUID(int=3),
        store_id=UUID(int=4),
        version=1,
    )
    assert set(event.payload) == {
        "price_id",
        "product_id",
        "variant_id",
        "store_id",
        "version",
        "timestamp",
    }
    assert not {"base_price", "sale_price", "currency_code"} & set(event.payload)


def test_product_price_model_declares_constraints_and_indexes() -> None:
    table = cast(Table, ProductPriceModel.__table__)
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}
    assert {
        "ck_product_prices_base_nonnegative",
        "ck_product_prices_sale_not_above_base",
        "ck_product_prices_compare_not_below_base",
        "ck_product_prices_effective_period",
        "ck_product_prices_deleted_archived",
    } <= constraint_names
    assert {
        "ix_product_prices_store",
        "ix_product_prices_product",
        "ix_product_prices_variant",
        "ix_product_prices_status",
        "ix_product_prices_currency",
        "ix_product_prices_effective_from",
        "ix_product_prices_effective_until",
        "uq_product_prices_active_variant_currency_period",
    } <= index_names


async def test_create_price_through_production_stack_emits_event_and_metric(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    logger = logging.getLogger("app.modules.stores.infrastructure.events")
    handler = _EventLogHandler()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    before = _counter_value("fashion_network_price_created_total")

    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        try:
            response, price = await _create_price(
                client, headers, verified_store, product, product_variant
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

    assert response.headers["location"] == f"/api/v1/prices/{price.id}"
    assert price.id.version == 7
    assert price.store_id == verified_store.id
    assert price.product_id == product.id
    assert price.variant_id == product_variant.id
    assert price.currency_code == "INR"
    assert price.base_price == Decimal("1999.0000")
    assert price.sale_price == Decimal("1499.0000")
    assert price.status is PriceStatus.DRAFT
    assert price.version == 1

    model = await db_session.scalar(
        select(ProductPriceModel).where(ProductPriceModel.id == price.id)
    )
    assert model is not None
    assert model.created_by_id == authenticated_identity.user.id
    assert model.updated_by_id == authenticated_identity.user.id
    assert model.deleted_at is None
    assert db_session.in_transaction()
    assert "product_price.created" in handler.event_names
    assert _counter_value("fashion_network_price_created_total") == before + 1


async def test_price_detail_list_and_filters_are_owner_scoped(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        _, created = await _create_price(
            client, headers, verified_store, product, product_variant
        )
        detail_response = await client.get(
            f"/api/v1/prices/{created.id}", headers=headers
        )
        list_response = await client.get(
            "/api/v1/prices",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "variant_id": str(product_variant.id),
                "currency": "inr",
                "status": "draft",
            },
        )
        missing_response = await client.get(
            f"/api/v1/prices/{UUID(int=99)}", headers=headers
        )

    assert detail_response.status_code == 200
    assert ProductPriceResponse.model_validate(detail_response.json()) == created
    assert list_response.status_code == 200
    page = ProductPriceListResponse.model_validate(list_response.json())
    assert page.items == [created]
    assert page.page.total == 1
    assert not page.page.has_more
    assert missing_response.status_code == 404


async def test_price_ownership_currency_period_and_amount_validation(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        wrong_store = await client.post(
            "/api/v1/prices",
            headers=headers,
            json=_price_payload(
                verified_store,
                product,
                product_variant,
                store_id=str(UUID(int=99)),
            ),
        )
        wrong_variant = await client.post(
            "/api/v1/prices",
            headers=headers,
            json=_price_payload(
                verified_store,
                product,
                product_variant,
                variant_id=str(UUID(int=99)),
            ),
        )
        invalid_currency = await client.post(
            "/api/v1/prices",
            headers=headers,
            json=_price_payload(
                verified_store,
                product,
                product_variant,
                currency_code="US1",
            ),
        )
        invalid_amount = await client.post(
            "/api/v1/prices",
            headers=headers,
            json=_price_payload(
                verified_store,
                product,
                product_variant,
                base_price="100.00",
                sale_price="101.00",
            ),
        )
        invalid_period = await client.post(
            "/api/v1/prices",
            headers=headers,
            json=_price_payload(
                verified_store,
                product,
                product_variant,
                effective_from=now.isoformat(),
                effective_until=(now - timedelta(days=1)).isoformat(),
            ),
        )

    assert wrong_store.status_code == 404
    assert wrong_variant.status_code == 404
    assert invalid_currency.status_code == 422
    assert invalid_amount.status_code == 422
    assert invalid_period.status_code == 422


async def test_price_lifecycle_active_uniqueness_and_update_optimistic_locking(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    logger = logging.getLogger("app.modules.stores.infrastructure.events")
    handler = _EventLogHandler()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    activated_before = _counter_value("fashion_network_price_activated_total")
    updated_before = _counter_value("fashion_network_price_updated_total")

    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        _, first = await _create_price(
            client, headers, verified_store, product, product_variant
        )
        _, second = await _create_price(
            client, headers, verified_store, product, product_variant
        )
        activated_response = await client.patch(
            f"/api/v1/prices/{first.id}",
            headers=headers,
            json={"status": "active", "version": first.version},
        )
        duplicate_response = await client.patch(
            f"/api/v1/prices/{second.id}",
            headers=headers,
            json={"status": "active", "version": second.version},
        )
        stale_response = await client.patch(
            f"/api/v1/prices/{first.id}",
            headers=headers,
            json={"base_price": "1899.00", "version": first.version},
        )
        activated = ProductPriceResponse.model_validate(activated_response.json())
        archived_response = await client.patch(
            f"/api/v1/prices/{first.id}",
            headers=headers,
            json={"status": "archived", "version": activated.version},
        )
        archived = ProductPriceResponse.model_validate(archived_response.json())
        reactivate_response = await client.patch(
            f"/api/v1/prices/{first.id}",
            headers=headers,
            json={"status": "active", "version": archived.version},
        )
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert activated_response.status_code == 200
    assert activated.status is PriceStatus.ACTIVE
    assert activated.version == 2
    assert duplicate_response.status_code == 409
    assert stale_response.status_code == 409
    assert archived_response.status_code == 200
    assert archived.status is PriceStatus.ARCHIVED
    assert archived.version == 3
    assert reactivate_response.status_code == 409
    assert {
        "product_price.updated",
        "product_price.activated",
        "product_price.archived",
    } <= set(handler.event_names)
    assert _counter_value("fashion_network_price_activated_total") == (
        activated_before + 1
    )
    assert _counter_value("fashion_network_price_updated_total") == (updated_before + 2)


async def test_price_delete_soft_deletion_and_stale_conflict(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    deleted_before = _counter_value("fashion_network_price_deleted_total")
    logger = logging.getLogger("app.modules.stores.infrastructure.events")
    handler = _EventLogHandler()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        _, created = await _create_price(
            client, headers, verified_store, product, product_variant
        )
        update_response = await client.patch(
            f"/api/v1/prices/{created.id}",
            headers=headers,
            json={"tax_class": "reduced", "version": created.version},
        )
        updated = ProductPriceResponse.model_validate(update_response.json())
        stale_delete = await client.delete(
            f"/api/v1/prices/{created.id}",
            headers=headers,
            params={"version": created.version},
        )
        delete_response = await client.delete(
            f"/api/v1/prices/{created.id}",
            headers=headers,
            params={"version": updated.version},
        )
        hidden_response = await client.get(
            f"/api/v1/prices/{created.id}", headers=headers
        )
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert update_response.status_code == 200
    assert updated.version == 2
    assert stale_delete.status_code == 409
    assert delete_response.status_code == 204
    assert hidden_response.status_code == 404
    model = await db_session.scalar(
        select(ProductPriceModel).where(ProductPriceModel.id == created.id)
    )
    assert model is not None
    assert model.status is PriceStatus.ARCHIVED
    assert model.deleted_at is not None
    assert model.deleted_by_id == authenticated_identity.user.id
    assert model.updated_by_id == authenticated_identity.user.id
    assert model.version == 3
    assert _counter_value("fashion_network_price_deleted_total") == deleted_before + 1
    assert {"product_price.archived", "product_price.deleted"} <= set(
        handler.event_names
    )


def test_pricing_openapi_documents_routes_filters_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/prices", "price:create"),
        ("get", "/api/v1/prices", "price:view"),
        ("get", "/api/v1/prices/{price_id}", "price:view"),
        ("patch", "/api/v1/prices/{price_id}", "price:update"),
        ("delete", "/api/v1/prices/{price_id}", "price:update"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
    parameters = schema["paths"]["/api/v1/prices"]["get"]["parameters"]
    assert {
        "store_id",
        "product_id",
        "variant_id",
        "currency",
        "status",
        "effective_at",
        "offset",
        "limit",
    } <= {parameter["name"] for parameter in parameters}
