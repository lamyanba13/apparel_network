from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import generate_latest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
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
from app.modules.pricing.api.price_list_schemas import (
    PriceAssignmentResponse,
    PriceListPageResponse,
    PriceListResponse,
    ResolvedPriceResponse,
)
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.pricing.domain import (
    CustomerGroup,
    PriceListCreated,
    PriceListStatus,
    PriceResolved,
    ResolutionLevel,
)
from app.modules.pricing.infrastructure.models import (
    PriceListAssignmentModel,
    PriceListModel,
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
        identity.user.id, "store_owner", assigned_by_id=identity.user.id
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


async def _create_price(
    client: AsyncClient,
    headers: dict[str, str],
    store: Store,
    product: Product,
    variant_id: UUID | None,
    *,
    currency: str = "INR",
    amount: str = "100.0000",
) -> ProductPriceResponse:
    created = await client.post(
        "/api/v1/prices",
        headers=headers,
        json={
            "store_id": str(store.id),
            "product_id": str(product.id),
            "variant_id": str(variant_id) if variant_id else None,
            "currency_code": currency,
            "base_price": amount,
            "tax_class": "standard",
            "status": "draft",
        },
    )
    assert created.status_code == 201, created.text
    price = ProductPriceResponse.model_validate(created.json())
    activated = await client.patch(
        f"/api/v1/prices/{price.id}",
        headers=headers,
        json={"status": "active", "version": price.version},
    )
    assert activated.status_code == 200, activated.text
    return ProductPriceResponse.model_validate(activated.json())


async def _create_price_list(
    client: AsyncClient,
    headers: dict[str, str],
    store: Store,
    *,
    slug: str,
    currency: str = "INR",
    priority: int = 0,
    customer_group: str = "public",
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    activate: bool = True,
    is_default: bool = False,
) -> PriceListResponse:
    response = await client.post(
        "/api/v1/price-lists",
        headers=headers,
        json={
            "store_id": str(store.id),
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "currency_code": currency,
            "priority": priority,
            "status": "draft",
            "customer_group": customer_group,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "effective_until": effective_until.isoformat() if effective_until else None,
        },
    )
    assert response.status_code == 201, response.text
    price_list = PriceListResponse.model_validate(response.json())
    if not activate:
        return price_list
    update = await client.patch(
        f"/api/v1/price-lists/{price_list.id}",
        headers=headers,
        json={
            "status": "active",
            "is_default": is_default,
            "version": price_list.version,
        },
    )
    assert update.status_code == 200, update.text
    return PriceListResponse.model_validate(update.json())


async def _assign(
    client: AsyncClient,
    headers: dict[str, str],
    price_list_id: UUID,
    price_id: UUID,
) -> PriceAssignmentResponse:
    response = await client.post(
        f"/api/v1/price-lists/{price_list_id}/prices",
        headers=headers,
        json={"price_id": str(price_id)},
    )
    assert response.status_code == 201, response.text
    return PriceAssignmentResponse.model_validate(response.json())


def test_price_list_events_are_identifier_only() -> None:
    event = PriceListCreated(
        price_list_id=UUID(int=1),
        price_id=None,
        store_id=UUID(int=2),
        version=1,
    )
    assert set(event.payload) == {
        "price_list_id",
        "price_id",
        "store_id",
        "version",
        "timestamp",
    }
    resolved = PriceResolved(
        price_list_id=UUID(int=1),
        price_id=UUID(int=3),
        store_id=UUID(int=2),
        version=2,
    )
    assert resolved.payload["price_id"] == str(UUID(int=3))


def test_price_list_models_declare_required_constraints_and_indexes() -> None:
    table = cast(Table, PriceListModel.__table__)
    names = {constraint.name for constraint in table.constraints}
    indexes = {index.name for index in table.indexes}
    assert {
        "ck_price_lists_priority_nonnegative",
        "ck_price_lists_effective_period",
        "ck_price_lists_default_active",
        "ck_price_lists_default_public",
        "uq_price_lists_store_slug",
    } <= names
    assert {
        "ix_price_lists_store",
        "ix_price_lists_currency",
        "ix_price_lists_priority",
        "ix_price_lists_status",
        "ix_price_lists_effective_from",
        "ix_price_lists_effective_until",
        "uq_price_lists_default_store_currency",
    } <= indexes


async def test_price_list_crud_assignment_ownership_and_optimistic_locking(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    logger = logging.getLogger("app.modules.stores.infrastructure.events")
    handler = _EventLogHandler()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    created_before = _counter_value("fashion_network_price_list_created_total")
    assigned_before = _counter_value("fashion_network_price_assigned_total")
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        draft = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="retail-inr",
            activate=False,
        )
        detail = await client.get(f"/api/v1/price-lists/{draft.id}", headers=headers)
        listing = await client.get(
            "/api/v1/price-lists",
            headers=headers,
            params={"store_id": str(verified_store.id), "currency": "inr"},
        )
        activated_response = await client.patch(
            f"/api/v1/price-lists/{draft.id}",
            headers=headers,
            json={"status": "active", "is_default": True, "version": 1},
        )
        activated = PriceListResponse.model_validate(activated_response.json())
        stale = await client.patch(
            f"/api/v1/price-lists/{draft.id}",
            headers=headers,
            json={"priority": 10, "version": 1},
        )
        price = await _create_price(
            client, headers, verified_store, product, product_variant.id
        )
        assignment = await _assign(client, headers, draft.id, price.id)
        duplicate = await client.post(
            f"/api/v1/price-lists/{draft.id}/prices",
            headers=headers,
            json={"price_id": str(price.id)},
        )
        unassigned = await client.delete(
            f"/api/v1/price-lists/{draft.id}/prices/{price.id}", headers=headers
        )
        replacement_assignment = await _assign(client, headers, draft.id, price.id)
        usd_price = await _create_price(
            client,
            headers,
            verified_store,
            product,
            None,
            currency="USD",
        )
        wrong_currency_assignment = await client.post(
            f"/api/v1/price-lists/{draft.id}/prices",
            headers=headers,
            json={"price_id": str(usd_price.id)},
        )
        wrong_store = await client.post(
            "/api/v1/price-lists",
            headers=headers,
            json={
                "store_id": str(UUID(int=99)),
                "name": "Wrong Store",
                "slug": "wrong-store",
                "currency_code": "INR",
            },
        )
        second = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="second-default",
            activate=False,
        )
        default_conflict = await client.patch(
            f"/api/v1/price-lists/{second.id}",
            headers=headers,
            json={"status": "active", "is_default": True, "version": 1},
        )
        second_active_response = await client.patch(
            f"/api/v1/price-lists/{second.id}",
            headers=headers,
            json={"status": "active", "version": 1},
        )
        second_active = PriceListResponse.model_validate(second_active_response.json())
        second_archived_response = await client.patch(
            f"/api/v1/price-lists/{second.id}",
            headers=headers,
            json={"status": "archived", "version": second_active.version},
        )
        second_archived = PriceListResponse.model_validate(
            second_archived_response.json()
        )
        reactivation = await client.patch(
            f"/api/v1/price-lists/{second.id}",
            headers=headers,
            json={"status": "active", "version": second_archived.version},
        )
        stale_delete = await client.delete(
            f"/api/v1/price-lists/{draft.id}",
            headers=headers,
            params={"version": 1},
        )
        delete_response = await client.delete(
            f"/api/v1/price-lists/{draft.id}",
            headers=headers,
            params={"version": activated.version},
        )
        hidden = await client.get(f"/api/v1/price-lists/{draft.id}", headers=headers)
    logger.removeHandler(handler)
    logger.setLevel(previous_level)

    assert detail.status_code == 200
    page = PriceListPageResponse.model_validate(listing.json())
    assert page.page.total == 1 and page.items[0].id == draft.id
    assert activated.status is PriceListStatus.ACTIVE and activated.is_default
    assert stale.status_code == 409
    assert assignment.price_list_id == draft.id and assignment.price_id == price.id
    assert duplicate.status_code == 409
    assert unassigned.status_code == 204
    assert replacement_assignment.id != assignment.id
    assert wrong_currency_assignment.status_code == 404
    assert wrong_store.status_code == 404
    assert default_conflict.status_code == 409
    assert second_active.status is PriceListStatus.ACTIVE
    assert second_archived.status is PriceListStatus.ARCHIVED
    assert reactivation.status_code == 409
    assert stale_delete.status_code == 409
    assert delete_response.status_code == 204
    assert hidden.status_code == 404
    model = await db_session.get(PriceListModel, draft.id)
    assert model is not None
    assert model.status is PriceListStatus.ARCHIVED
    assert model.deleted_at is not None
    assert model.deleted_by_id == authenticated_identity.user.id
    removed_assignment = await db_session.get(PriceListAssignmentModel, assignment.id)
    persisted_assignment = await db_session.get(
        PriceListAssignmentModel, replacement_assignment.id
    )
    assert removed_assignment is None
    assert persisted_assignment is not None
    assert {
        "price_list.created",
        "price_list.updated",
        "price_list.price_assigned",
        "price_list.price_unassigned",
        "price_list.archived",
    } <= set(handler.event_names)
    assert _counter_value("fashion_network_price_list_created_total") == (
        created_before + 2
    )
    assert _counter_value("fashion_network_price_assigned_total") == assigned_before + 2


async def test_resolver_precedence_scheduling_currency_groups_and_fallback(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    resolved_before = _counter_value("fashion_network_price_resolved_total")
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        product_price = await _create_price(
            client, headers, verified_store, product, None, amount="80.0000"
        )
        variant_price = await _create_price(
            client,
            headers,
            verified_store,
            product,
            product_variant.id,
            amount="70.0000",
        )
        product_list = await _create_price_list(
            client, headers, verified_store, slug="product-high", priority=999
        )
        older_variant_list = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="variant-old",
            priority=20,
            effective_from=now - timedelta(days=5),
        )
        newer_variant_list = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="variant-new",
            priority=20,
            effective_from=now - timedelta(days=1),
        )
        expired_list = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="expired",
            priority=1000,
            effective_from=now - timedelta(days=10),
            effective_until=now - timedelta(days=2),
        )
        for price_list, price in (
            (product_list, product_price),
            (older_variant_list, variant_price),
            (newer_variant_list, variant_price),
            (expired_list, variant_price),
        ):
            await _assign(client, headers, price_list.id, price.id)
        response = await client.get(
            "/api/v1/pricing/resolve",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "variant_id": str(product_variant.id),
                "currency": "INR",
                "customer_group": "public",
                "timestamp": now.isoformat(),
            },
        )
        vip_list = await _create_price_list(
            client,
            headers,
            verified_store,
            slug="vip-list",
            priority=1,
            customer_group="vip",
        )
        await _assign(client, headers, vip_list.id, variant_price.id)
        vip_response = await client.get(
            "/api/v1/pricing/resolve",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "variant_id": str(product_variant.id),
                "currency": "INR",
                "customer_group": "vip",
                "timestamp": now.isoformat(),
            },
        )
        usd_price = await _create_price(
            client,
            headers,
            verified_store,
            product,
            None,
            currency="USD",
            amount="25.0000",
        )
        fallback_response = await client.get(
            "/api/v1/pricing/resolve",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "variant_id": str(product_variant.id),
                "currency": "USD",
                "timestamp": now.isoformat(),
            },
        )
        missing_currency = await client.get(
            "/api/v1/pricing/resolve",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "currency": "EUR",
            },
        )
        invalid_currency = await client.get(
            "/api/v1/pricing/resolve",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "product_id": str(product.id),
                "currency": "ZZZ",
            },
        )

    assert response.status_code == 200
    resolved = ResolvedPriceResponse.model_validate(response.json())
    assert resolved.price_id == variant_price.id
    assert resolved.price_list_id == newer_variant_list.id
    assert resolved.resolution_level is ResolutionLevel.VARIANT
    assert resolved.amount == Decimal("70.0000")
    assert vip_response.status_code == 200
    vip = ResolvedPriceResponse.model_validate(vip_response.json())
    assert vip.price_list_id == vip_list.id
    assert vip.customer_group is CustomerGroup.VIP
    assert fallback_response.status_code == 200
    fallback = ResolvedPriceResponse.model_validate(fallback_response.json())
    assert fallback.price_id == usd_price.id
    assert fallback.price_list_id is None
    assert fallback.resolution_level is ResolutionLevel.DEFAULT_STORE
    assert missing_currency.status_code == 404
    assert invalid_currency.status_code == 422
    assert _counter_value("fashion_network_price_resolved_total") == (
        resolved_before + 3
    )


def test_price_list_openapi_documents_routes_permissions_and_resolver(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/price-lists", "price:list:create"),
        ("get", "/api/v1/price-lists", "price:list:view"),
        ("get", "/api/v1/price-lists/{price_list_id}", "price:list:view"),
        ("patch", "/api/v1/price-lists/{price_list_id}", "price:list:update"),
        ("delete", "/api/v1/price-lists/{price_list_id}", "price:list:update"),
        ("post", "/api/v1/price-lists/{price_list_id}/prices", "price:list:update"),
        (
            "delete",
            "/api/v1/price-lists/{price_list_id}/prices/{price_id}",
            "price:list:update",
        ),
        ("get", "/api/v1/pricing/resolve", "price:resolve"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
    resolver_parameters = schema["paths"]["/api/v1/pricing/resolve"]["get"][
        "parameters"
    ]
    assert {
        "store_id",
        "product_id",
        "variant_id",
        "currency",
        "customer_group",
        "timestamp",
    } <= {parameter["name"] for parameter in resolver_parameters}
