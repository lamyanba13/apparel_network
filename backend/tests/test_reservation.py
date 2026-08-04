from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.api.schemas import CartResponse
from app.modules.checkout.api.schemas import CheckoutResponse
from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.inventory.api.schemas import InventoryResponse
from app.modules.orders.api.schemas import OrderResponse
from app.modules.payments.api.schemas import PaymentIntentResponse
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.reservations.api.schemas import (
    ReservationDetailResponse,
    ReservationListResponse,
    ReservationResponse,
    ReservationStatusResponse,
)
from app.modules.reservations.domain import (
    ReservationActivated,
    ReservationConsumed,
    ReservationCreated,
    ReservationExpired,
    ReservationReleased,
    ReservationStatus,
)
from app.modules.reservations.infrastructure.models import (
    InventoryReservationItemModel,
    InventoryReservationModel,
)
from app.modules.stores.domain import Store
from tests.test_payment import (
    _authorized_client,
    _sample_value,
    _second_identity,
)

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


async def _create_captured_order(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    store_id: UUID,
    variant_id: UUID,
    quantity: int,
    key: str,
    capture: bool = True,
) -> tuple[OrderResponse, PaymentIntentResponse]:
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
        json={
            "variant_id": str(variant_id),
            "quantity": quantity,
            "version": cart.version,
        },
    )
    assert item_response.status_code == 201, item_response.text
    checkout_response = await client.post(
        "/api/v1/checkout", headers=headers, json={"cart_id": str(cart.id)}
    )
    assert checkout_response.status_code == 201, checkout_response.text
    checkout = CheckoutResponse.model_validate(checkout_response.json())
    checkout_confirm = await client.post(
        f"/api/v1/checkout/{checkout.id}/confirm",
        headers=headers,
        json={"version": checkout.version},
    )
    assert checkout_confirm.status_code == 200, checkout_confirm.text
    order_response = await client.post(
        "/api/v1/orders",
        headers=headers,
        json={"checkout_session_id": str(checkout.id)},
    )
    assert order_response.status_code == 201, order_response.text
    order = OrderResponse.model_validate(order_response.json())
    payment_response = await client.post(
        "/api/v1/payments",
        headers={**headers, "Idempotency-Key": key},
        json={"order_id": str(order.id)},
    )
    assert payment_response.status_code == 201, payment_response.text
    payment = PaymentIntentResponse.model_validate(payment_response.json())
    authorized_response = await client.post(
        f"/api/v1/payments/{payment.id}/authorize",
        headers=headers,
        json={"version": payment.version},
    )
    assert authorized_response.status_code == 200, authorized_response.text
    authorized = PaymentIntentResponse.model_validate(authorized_response.json())
    if not capture:
        return order, authorized
    captured_response = await client.post(
        f"/api/v1/payments/{payment.id}/capture",
        headers=headers,
        json={"version": authorized.version},
    )
    assert captured_response.status_code == 200, captured_response.text
    return order, PaymentIntentResponse.model_validate(captured_response.json())


def test_reservation_domain_events_and_models() -> None:
    event_names = {
        event_type(
            reservation_id=UUID(int=1),
            order_id=UUID(int=2),
            payment_id=UUID(int=3),
            customer_id=UUID(int=4),
            store_id=UUID(int=5),
            version=1,
        ).event_name
        for event_type in (
            ReservationCreated,
            ReservationActivated,
            ReservationReleased,
            ReservationExpired,
            ReservationConsumed,
        )
    }
    assert event_names == {
        "reservation.created",
        "reservation.activated",
        "reservation.released",
        "reservation.expired",
        "reservation.consumed",
    }
    reservation_table = cast(Table, InventoryReservationModel.__table__)
    item_table = cast(Table, InventoryReservationItemModel.__table__)
    assert "uq_inventory_reservations_active_order" in {
        index.name for index in reservation_table.indexes
    }
    assert "uq_inventory_reservation_items_inventory" in {
        constraint.name for constraint in item_table.constraints
    }


async def test_reservation_production_stack_capacity_expiration_and_lifecycle(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _sample_value("fashion_network_reservation_created_total")
    consumed_before = _sample_value("fashion_network_reservation_consumed_total")
    released_before = _sample_value("fashion_network_reservation_released_total")
    expired_before = _sample_value("fashion_network_reservation_expired_total")
    duration_before = _sample_value(
        "fashion_network_reservation_duration_seconds_count"
    )

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
        draft_price = ProductPriceResponse.model_validate(price_response.json())
        activation = await client.patch(
            f"/api/v1/prices/{draft_price.id}",
            headers=headers,
            json={"status": "active", "version": draft_price.version},
        )
        assert activation.status_code == 200, activation.text

        order, authorized_payment = await _create_captured_order(
            client,
            headers,
            store_id=verified_store.id,
            variant_id=product_variant.id,
            quantity=2,
            key="reservation-pay-0001",
            capture=False,
        )
        premature = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(order.id),
                "payment_id": str(authorized_payment.id),
            },
        )
        capture_response = await client.post(
            f"/api/v1/payments/{authorized_payment.id}/capture",
            headers=headers,
            json={"version": authorized_payment.version},
        )
        assert capture_response.status_code == 200, capture_response.text
        captured_payment = PaymentIntentResponse.model_validate(capture_response.json())
        create_response = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(order.id),
                "payment_id": str(captured_payment.id),
            },
        )
        assert create_response.status_code == 201, create_response.text
        reservation = ReservationResponse.model_validate(create_response.json())
        duplicate = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(order.id),
                "payment_id": str(captured_payment.id),
            },
        )
        detail_response = await client.get(
            f"/api/v1/reservations/{reservation.id}", headers=headers
        )
        detail = ReservationDetailResponse.model_validate(detail_response.json())
        list_response = await client.get("/api/v1/reservations", headers=headers)
        status_response = await client.get(
            f"/api/v1/reservations/{reservation.id}/status", headers=headers
        )
        active_status = ReservationStatusResponse.model_validate(status_response.json())

        large_order, large_payment = await _create_captured_order(
            client,
            headers,
            store_id=verified_store.id,
            variant_id=product_variant.id,
            quantity=19,
            key="reservation-pay-0002",
        )
        insufficient = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(large_order.id),
                "payment_id": str(large_payment.id),
            },
        )
        stale_consume = await client.post(
            f"/api/v1/reservations/{reservation.id}/consume",
            headers=headers,
            json={"version": reservation.version + 1},
        )
        consume_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/consume",
            headers=headers,
            json={"version": reservation.version},
        )
        assert consume_response.status_code == 200, consume_response.text
        consumed = ReservationResponse.model_validate(consume_response.json())
        repeat_consume = await client.post(
            f"/api/v1/reservations/{reservation.id}/consume",
            headers=headers,
            json={"version": consumed.version},
        )

        release_order, release_payment = await _create_captured_order(
            client,
            headers,
            store_id=verified_store.id,
            variant_id=product_variant.id,
            quantity=2,
            key="reservation-pay-0003",
        )
        release_create = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(release_order.id),
                "payment_id": str(release_payment.id),
            },
        )
        assert release_create.status_code == 201, release_create.text
        releasable = ReservationResponse.model_validate(release_create.json())
        stale_release = await client.post(
            f"/api/v1/reservations/{releasable.id}/release",
            headers=headers,
            json={"version": releasable.version + 1},
        )
        release_response = await client.post(
            f"/api/v1/reservations/{releasable.id}/release",
            headers=headers,
            json={"version": releasable.version},
        )
        assert release_response.status_code == 200, release_response.text
        released = ReservationResponse.model_validate(release_response.json())
        hidden_released = await client.get(
            f"/api/v1/reservations/{releasable.id}", headers=headers
        )

        expiry_order, expiry_payment = await _create_captured_order(
            client,
            headers,
            store_id=verified_store.id,
            variant_id=product_variant.id,
            quantity=2,
            key="reservation-pay-0004",
        )
        expiry_create = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "order_id": str(expiry_order.id),
                "payment_id": str(expiry_payment.id),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=2)).isoformat(),
            },
        )
        assert expiry_create.status_code == 201, expiry_create.text
        expiring = ReservationResponse.model_validate(expiry_create.json())
        await asyncio.sleep(2.1)
        expired_response = await client.get(
            f"/api/v1/reservations/{expiring.id}/status", headers=headers
        )
        assert expired_response.status_code == 200, expired_response.text
        expired = ReservationStatusResponse.model_validate(expired_response.json())
        hidden_expired = await client.get(
            f"/api/v1/reservations/{expiring.id}", headers=headers
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
        hidden_cross_user = await client.get(
            f"/api/v1/reservations/{reservation.id}", headers=second_headers
        )

    assert premature.status_code == 409
    assert reservation.status is ReservationStatus.ACTIVE
    assert reservation.version == 2
    assert reservation.expires_at >= reservation.created_at + timedelta(minutes=29)
    assert duplicate.status_code == 409
    assert len(detail.items) == 1
    assert detail.items[0].inventory_item_id == inventory.id
    assert detail.items[0].variant_id == product_variant.id
    assert detail.items[0].quantity == 2
    assert detail.items[0].inventory_version == inventory.version
    page = ReservationListResponse.model_validate(list_response.json())
    assert page.page.total == 1 and page.items[0].id == reservation.id
    assert active_status.status is ReservationStatus.ACTIVE
    assert insufficient.status_code == 409
    assert stale_consume.status_code == 409
    assert consumed.status is ReservationStatus.CONSUMED
    assert consumed.consumed_at is not None
    assert repeat_consume.status_code == 409
    assert stale_release.status_code == 409
    assert released.status is ReservationStatus.RELEASED
    assert released.released_at is not None
    assert hidden_released.status_code == 404
    assert expired.status is ReservationStatus.EXPIRED
    assert hidden_expired.status_code == 404
    assert hidden_cross_user.status_code == 404
    assert inventory_after.quantity_on_hand == 20
    assert inventory_after.quantity_reserved == 0
    assert inventory_after.quantity_available == 20
    assert inventory_after.version == inventory.version

    consumed_model = await db_session.get(InventoryReservationModel, reservation.id)
    assert consumed_model is not None
    assert consumed_model.status is ReservationStatus.CONSUMED
    assert consumed_model.deleted_at is None
    released_model = await db_session.get(InventoryReservationModel, releasable.id)
    assert released_model is not None and released_model.deleted_at is not None
    expired_model = await db_session.get(InventoryReservationModel, expiring.id)
    assert expired_model is not None
    assert expired_model.status is ReservationStatus.EXPIRED
    assert expired_model.deleted_at is not None

    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "reservation",
                EventOutboxModel.aggregate_id.in_(
                    [reservation.id, releasable.id, expiring.id]
                ),
            )
        )
    ).all()
    assert {event.event_name for event in outbox} == {
        "reservation.created",
        "reservation.activated",
        "reservation.consumed",
        "reservation.released",
        "reservation.expired",
    }
    assert all(
        set(event.payload)
        == {
            "reservation_id",
            "order_id",
            "payment_id",
            "customer_id",
            "store_id",
            "version",
            "timestamp",
        }
        for event in outbox
    )
    assert (
        _sample_value("fashion_network_reservation_created_total") == created_before + 3
    )
    assert (
        _sample_value("fashion_network_reservation_consumed_total")
        == consumed_before + 1
    )
    assert (
        _sample_value("fashion_network_reservation_released_total")
        == released_before + 1
    )
    assert (
        _sample_value("fashion_network_reservation_expired_total") == expired_before + 1
    )
    assert (
        _sample_value("fashion_network_reservation_duration_seconds_count")
        == duration_before + 3
    )


def test_reservation_openapi_documents_routes_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/reservations", "reservation:create"),
        ("get", "/api/v1/reservations", "reservation:view"),
        ("get", "/api/v1/reservations/{reservation_id}", "reservation:view"),
        (
            "post",
            "/api/v1/reservations/{reservation_id}/release",
            "reservation:release",
        ),
        (
            "post",
            "/api/v1/reservations/{reservation_id}/consume",
            "reservation:consume",
        ),
        (
            "get",
            "/api/v1/reservations/{reservation_id}/status",
            "reservation:view",
        ),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
