from __future__ import annotations

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
from app.modules.cart.api.schemas import CartResponse
from app.modules.checkout.api.schemas import CheckoutResponse
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
from app.modules.orders.api.schemas import OrderResponse
from app.modules.orders.domain import OrderStatus
from app.modules.payments.api.schemas import (
    PaymentDetailResponse,
    PaymentIntentResponse,
    PaymentListResponse,
    PaymentStatusResponse,
)
from app.modules.payments.application.gateways import PaymentGateway
from app.modules.payments.domain import (
    Money,
    PaymentAuthorized,
    PaymentCancelled,
    PaymentCaptured,
    PaymentCreated,
    PaymentFailed,
    PaymentProvider,
    PaymentSnapshot,
    PaymentStatus,
    PaymentTransactionType,
)
from app.modules.payments.infrastructure.gateway import NullPaymentGateway
from app.modules.payments.infrastructure.models import (
    PaymentIntentModel,
    PaymentTransactionModel,
)
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


def _sample_value(name: str) -> float:
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
    role: str,
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
            device_name="Payment ownership device",
            display_name="Payment ownership device",
            ip_address=ip_address("127.0.0.5"),
            user_agent="fashion-network-payment-test",
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


async def _create_pending_order(
    client: AsyncClient,
    headers: dict[str, str],
    store_id: UUID,
    variant_id: UUID,
) -> OrderResponse:
    cart_response = await client.post(
        "/api/v1/cart",
        headers=headers,
        json={"store_id": str(store_id), "currency": "INR"},
    )
    assert cart_response.status_code == 201, cart_response.text
    cart = CartResponse.model_validate(cart_response.json())
    item_response = await client.post(
        f"/api/v1/cart/{cart.id}/items",
        headers=headers,
        json={"variant_id": str(variant_id), "quantity": 2, "version": cart.version},
    )
    assert item_response.status_code == 201, item_response.text
    checkout_response = await client.post(
        "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
    )
    assert checkout_response.status_code == 201, checkout_response.text
    checkout = CheckoutResponse.model_validate(checkout_response.json())
    confirm_response = await client.post(
        f"/api/v1/checkout/{checkout.id}/confirm",
        headers=headers,
        json={"version": checkout.version},
    )
    assert confirm_response.status_code == 200, confirm_response.text
    order_response = await client.post(
        "/api/v1/orders",
        headers=headers,
        json={"checkout_session_id": str(checkout.id)},
    )
    assert order_response.status_code == 201, order_response.text
    return OrderResponse.model_validate(order_response.json())


async def test_payment_domain_gateway_events_and_models() -> None:
    snapshot = PaymentSnapshot(
        order_id=UUID(int=1),
        customer_id=UUID(int=2),
        store_id=UUID(int=3),
        money=Money(Decimal("99.5000"), "inr"),
    )
    assert snapshot.money.currency == "INR"
    with pytest.raises(ValueError):
        Money(Decimal("NaN"), "INR")
    gateway: PaymentGateway = NullPaymentGateway()
    created = await gateway.create_intent(
        payment_id=UUID(int=4),
        amount=snapshot.money.amount,
        currency=snapshot.money.currency,
        idempotency_key="payment-domain-01",
    )
    authorized = await gateway.authorize(
        payment_id=UUID(int=4), provider_reference=created.provider_reference
    )
    captured = await gateway.capture(
        payment_id=UUID(int=4), provider_reference=created.provider_reference
    )
    cancelled = await gateway.cancel(
        payment_id=UUID(int=4), provider_reference=created.provider_reference
    )
    checked = await gateway.status(
        payment_id=UUID(int=4),
        provider_reference=created.provider_reference,
        current_status=PaymentStatus.AUTHORIZED,
    )
    assert [
        created.status,
        authorized.status,
        captured.status,
        cancelled.status,
        checked.status,
    ] == [
        PaymentStatus.CREATED,
        PaymentStatus.AUTHORIZED,
        PaymentStatus.CAPTURED,
        PaymentStatus.CANCELLED,
        PaymentStatus.AUTHORIZED,
    ]
    event_names = {
        event_type(
            payment_id=UUID(int=1),
            order_id=UUID(int=2),
            customer_id=UUID(int=3),
            store_id=UUID(int=4),
            version=1,
        ).event_name
        for event_type in (
            PaymentCreated,
            PaymentAuthorized,
            PaymentCaptured,
            PaymentFailed,
            PaymentCancelled,
        )
    }
    assert event_names == {
        "payment.created",
        "payment.authorized",
        "payment.captured",
        "payment.failed",
        "payment.cancelled",
    }
    intent_table = cast(Table, PaymentIntentModel.__table__)
    transaction_table = cast(Table, PaymentTransactionModel.__table__)
    assert {"uq_payment_intents_idempotency", "uq_payment_intents_provider_ref"} <= {
        constraint.name for constraint in intent_table.constraints
    }
    assert "uq_payment_transactions_provider_id" in {
        constraint.name for constraint in transaction_table.constraints
    }


async def test_payment_production_stack_idempotency_ownership_lifecycle_and_order(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _sample_value("fashion_network_payment_created_total")
    authorized_before = _sample_value("fashion_network_payment_authorized_total")
    captured_before = _sample_value("fashion_network_payment_captured_total")
    cancelled_before = _sample_value("fashion_network_payment_cancelled_total")
    duration_before = _sample_value(
        "fashion_network_payment_processing_duration_seconds_count"
    )

    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
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
        order = await _create_pending_order(
            client, headers, verified_store.id, product_variant.id
        )

        missing_key = await client.post(
            "/api/v1/payments", headers=headers, json={"order_id": str(order.id)}
        )
        create_response = await client.post(
            "/api/v1/payments",
            headers={**headers, "Idempotency-Key": "payment-order-0001"},
            json={"order_id": str(order.id)},
        )
        assert create_response.status_code == 201, create_response.text
        payment = PaymentIntentResponse.model_validate(create_response.json())
        replay = await client.post(
            "/api/v1/payments",
            headers={**headers, "Idempotency-Key": "payment-order-0001"},
            json={"order_id": str(order.id)},
        )
        key_reuse = await client.post(
            "/api/v1/payments",
            headers={**headers, "Idempotency-Key": "payment-order-0001"},
            json={"order_id": str(uuid7())},
        )
        detail_response = await client.get(
            f"/api/v1/payments/{payment.id}", headers=headers
        )
        detail = PaymentDetailResponse.model_validate(detail_response.json())
        list_response = await client.get("/api/v1/payments", headers=headers)
        stale_authorize = await client.post(
            f"/api/v1/payments/{payment.id}/authorize",
            headers=headers,
            json={"version": payment.version + 1},
        )
        authorize_response = await client.post(
            f"/api/v1/payments/{payment.id}/authorize",
            headers=headers,
            json={"version": payment.version},
        )
        assert authorize_response.status_code == 200, authorize_response.text
        authorized = PaymentIntentResponse.model_validate(authorize_response.json())
        repeat_authorize = await client.post(
            f"/api/v1/payments/{payment.id}/authorize",
            headers=headers,
            json={"version": authorized.version},
        )
        status_response = await client.get(
            f"/api/v1/payments/{payment.id}/status", headers=headers
        )
        payment_status = PaymentStatusResponse.model_validate(status_response.json())
        stale_capture = await client.post(
            f"/api/v1/payments/{payment.id}/capture",
            headers=headers,
            json={"version": authorized.version + 1},
        )
        capture_response = await client.post(
            f"/api/v1/payments/{payment.id}/capture",
            headers=headers,
            json={"version": authorized.version},
        )
        assert capture_response.status_code == 200, capture_response.text
        captured = PaymentIntentResponse.model_validate(capture_response.json())
        repeat_capture = await client.post(
            f"/api/v1/payments/{payment.id}/capture",
            headers=headers,
            json={"version": captured.version},
        )
        confirmed_order_response = await client.get(
            f"/api/v1/orders/{order.id}", headers=headers
        )
        confirmed_order = OrderResponse.model_validate(confirmed_order_response.json())
        confirmed_payment = await client.post(
            "/api/v1/payments",
            headers={**headers, "Idempotency-Key": "payment-order-0002"},
            json={"order_id": str(order.id)},
        )
        inventory_after_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inventory_after = InventoryResponse.model_validate(
            inventory_after_response.json()
        )

    async with _authorized_client(
        async_client, second_identity, db_session, role="customer"
    ) as (client, second_headers):
        hidden = await client.get(
            f"/api/v1/payments/{payment.id}", headers=second_headers
        )
        second_order = await _create_pending_order(
            client, second_headers, verified_store.id, product_variant.id
        )
        second_create = await client.post(
            "/api/v1/payments",
            headers={**second_headers, "Idempotency-Key": "payment-order-0003"},
            json={"order_id": str(second_order.id)},
        )
        assert second_create.status_code == 201, second_create.text
        second_payment = PaymentIntentResponse.model_validate(second_create.json())
        stale_cancel = await client.post(
            f"/api/v1/payments/{second_payment.id}/cancel",
            headers=second_headers,
            json={"version": second_payment.version + 1},
        )
        cancel_response = await client.post(
            f"/api/v1/payments/{second_payment.id}/cancel",
            headers=second_headers,
            json={"version": second_payment.version},
        )
        assert cancel_response.status_code == 200, cancel_response.text
        cancelled = PaymentIntentResponse.model_validate(cancel_response.json())
        hidden_cancelled = await client.get(
            f"/api/v1/payments/{second_payment.id}", headers=second_headers
        )

    assert missing_key.status_code == 422
    assert replay.status_code == 201 and replay.json()["id"] == str(payment.id)
    assert key_reuse.status_code == 409
    assert payment.provider is PaymentProvider.NULL
    assert payment.status is PaymentStatus.CREATED
    assert payment.order_id == order.id
    assert payment.customer_id == authenticated_identity.user.id
    assert payment.store_id == verified_store.id
    assert payment.amount == order.subtotal == 251
    assert payment.currency == order.currency == "INR"
    assert payment.expires_at > payment.created_at
    assert len(detail.transactions) == 1
    assert detail.transactions[0].event_type is PaymentTransactionType.CREATED
    page = PaymentListResponse.model_validate(list_response.json())
    assert page.page.total == 1 and page.items[0].id == payment.id
    assert stale_authorize.status_code == 409
    assert authorized.status is PaymentStatus.AUTHORIZED
    assert authorized.authorized_at is not None
    assert repeat_authorize.status_code == 409
    assert payment_status.status is PaymentStatus.AUTHORIZED
    assert stale_capture.status_code == 409
    assert captured.status is PaymentStatus.CAPTURED
    assert captured.captured_at is not None
    assert repeat_capture.status_code == 409
    assert confirmed_order.status is OrderStatus.CONFIRMED
    assert confirmed_order.confirmed_at is not None
    assert confirmed_payment.status_code == 409
    assert inventory_after.quantity_on_hand == 10
    assert inventory_after.quantity_reserved == 0
    assert hidden.status_code == 404
    assert stale_cancel.status_code == 409
    assert cancelled.status is PaymentStatus.CANCELLED
    assert cancelled.cancelled_at is not None
    assert hidden_cancelled.status_code == 404

    persisted = await db_session.get(PaymentIntentModel, payment.id)
    assert persisted is not None and persisted.status is PaymentStatus.CAPTURED
    transactions = (
        await db_session.scalars(
            select(PaymentTransactionModel)
            .where(PaymentTransactionModel.payment_intent_id == payment.id)
            .order_by(PaymentTransactionModel.occurred_at)
        )
    ).all()
    assert [transaction.event_type for transaction in transactions] == [
        PaymentTransactionType.CREATED,
        PaymentTransactionType.AUTHORIZED,
        PaymentTransactionType.CAPTURED,
    ]
    assert transactions[0].provider_payload == {
        "gateway": "null",
        "operation": "created",
    }
    cancelled_model = await db_session.get(PaymentIntentModel, second_payment.id)
    assert cancelled_model is not None
    assert cancelled_model.status is PaymentStatus.CANCELLED
    assert cancelled_model.deleted_at is not None
    assert cancelled_model.deleted_by_id == second_identity.user.id

    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "payment",
                EventOutboxModel.aggregate_id.in_([payment.id, second_payment.id]),
            )
        )
    ).all()
    assert {event.event_name for event in outbox} == {
        "payment.created",
        "payment.authorized",
        "payment.captured",
        "payment.cancelled",
    }
    assert all(
        set(event.payload)
        == {"payment_id", "order_id", "customer_id", "store_id", "version", "timestamp"}
        for event in outbox
    )
    assert _sample_value("fashion_network_payment_created_total") == created_before + 2
    assert (
        _sample_value("fashion_network_payment_authorized_total")
        == authorized_before + 1
    )
    assert (
        _sample_value("fashion_network_payment_captured_total") == captured_before + 1
    )
    assert (
        _sample_value("fashion_network_payment_cancelled_total") == cancelled_before + 1
    )
    assert (
        _sample_value("fashion_network_payment_processing_duration_seconds_count")
        == duration_before + 6
    )


def test_payment_openapi_documents_routes_permissions_and_idempotency(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/payments", "payment:create"),
        ("get", "/api/v1/payments", "payment:view"),
        ("get", "/api/v1/payments/{payment_id}", "payment:view"),
        ("post", "/api/v1/payments/{payment_id}/authorize", "payment:update"),
        ("post", "/api/v1/payments/{payment_id}/capture", "payment:capture"),
        ("post", "/api/v1/payments/{payment_id}/cancel", "payment:cancel"),
        ("get", "/api/v1/payments/{payment_id}/status", "payment:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
    parameters = schema["paths"]["/api/v1/payments"]["post"]["parameters"]
    idempotency = next(
        value for value in parameters if value["name"] == "Idempotency-Key"
    )
    assert idempotency["in"] == "header" and idempotency["required"] is True
