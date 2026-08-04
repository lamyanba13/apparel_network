from __future__ import annotations

from decimal import Decimal
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.inventory.api.schemas import InventoryResponse
from app.modules.orders.api.schemas import OrderResponse
from app.modules.payments.api.schemas import PaymentIntentResponse
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.reservations.api.schemas import ReservationResponse
from app.modules.shipments.api.schemas import (
    ShipmentDetailResponse,
    ShipmentListResponse,
    ShipmentResponse,
    ShipmentTrackingResponse,
)
from app.modules.shipments.domain import (
    ShipmentCancelled,
    ShipmentCreated,
    ShipmentDelivered,
    ShipmentOutForDelivery,
    ShipmentPacked,
    ShipmentReturned,
    ShipmentReturnRequested,
    ShipmentShipped,
    ShipmentStatus,
)
from app.modules.shipments.infrastructure.models import (
    ShipmentModel,
    ShipmentPackageModel,
    ShipmentTrackingEventModel,
)
from app.modules.stores.domain import Store
from tests.test_payment import _authorized_client, _sample_value, _second_identity
from tests.test_reservation import _create_captured_order

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


def test_shipment_domain_events_models_and_gateway_contract() -> None:
    event_names = {
        event_type(
            shipment_id=UUID(int=1),
            order_id=UUID(int=2),
            reservation_id=UUID(int=3),
            payment_id=UUID(int=4),
            customer_id=UUID(int=5),
            store_id=UUID(int=6),
            version=1,
        ).event_name
        for event_type in (
            ShipmentCreated,
            ShipmentPacked,
            ShipmentShipped,
            ShipmentOutForDelivery,
            ShipmentDelivered,
            ShipmentCancelled,
            ShipmentReturnRequested,
            ShipmentReturned,
        )
    }
    assert event_names == {
        "shipment.created",
        "shipment.packed",
        "shipment.shipped",
        "shipment.out_for_delivery",
        "shipment.delivered",
        "shipment.cancelled",
        "shipment.return_requested",
        "shipment.returned",
    }
    shipment_table = cast(Table, ShipmentModel.__table__)
    package_table = cast(Table, ShipmentPackageModel.__table__)
    tracking_table = cast(Table, ShipmentTrackingEventModel.__table__)
    assert {"uq_shipments_order", "uq_shipments_reservation"} <= {
        constraint.name for constraint in shipment_table.constraints
    }
    assert "uq_shipment_packages_number" in {
        constraint.name for constraint in package_table.constraints
    }
    assert "ix_shipment_tracking_events_shipment" in {
        index.name for index in tracking_table.indexes
    }


async def _reservation(
    client: AsyncClient,
    headers: dict[str, str],
    store_id: UUID,
    variant_id: UUID,
    key: str,
) -> tuple[OrderResponse, PaymentIntentResponse, ReservationResponse]:
    order, payment = await _create_captured_order(
        client,
        headers,
        store_id=store_id,
        variant_id=variant_id,
        quantity=2,
        key=key,
    )
    response = await client.post(
        "/api/v1/reservations",
        headers=headers,
        json={"order_id": str(order.id), "payment_id": str(payment.id)},
    )
    assert response.status_code == 201, response.text
    return order, payment, ReservationResponse.model_validate(response.json())


async def test_shipment_production_stack_lifecycle_inventory_tracking_and_ownership(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    metric_names = (
        "fashion_network_shipment_created_total",
        "fashion_network_shipment_packed_total",
        "fashion_network_shipment_shipped_total",
        "fashion_network_shipment_delivered_total",
        "fashion_network_shipment_cancelled_total",
        "fashion_network_delivery_duration_seconds_count",
    )
    before = {name: _sample_value(name) for name in metric_names}

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
                "base_price": "100.0000",
                "tax_class": "standard",
                "status": "draft",
            },
        )
        assert price_response.status_code == 201, price_response.text
        draft = ProductPriceResponse.model_validate(price_response.json())
        activation = await client.patch(
            f"/api/v1/prices/{draft.id}",
            headers=headers,
            json={"status": "active", "version": draft.version},
        )
        assert activation.status_code == 200, activation.text

        order, payment, reservation = await _reservation(
            client,
            headers,
            verified_store.id,
            product_variant.id,
            "shipment-pay-0001",
        )
        premature = await client.post(
            "/api/v1/shipments",
            headers=headers,
            json={
                "order_id": str(order.id),
                "reservation_id": str(reservation.id),
                "payment_id": str(payment.id),
                "shipping_method": "standard",
            },
        )
        consume = await client.post(
            f"/api/v1/reservations/{reservation.id}/consume",
            headers=headers,
            json={"version": reservation.version},
        )
        assert consume.status_code == 200, consume.text
        create = await client.post(
            "/api/v1/shipments",
            headers=headers,
            json={
                "order_id": str(order.id),
                "reservation_id": str(reservation.id),
                "payment_id": str(payment.id),
                "shipping_method": "standard",
            },
        )
        assert create.status_code == 201, create.text
        shipment = ShipmentResponse.model_validate(create.json())
        duplicate = await client.post(
            "/api/v1/shipments",
            headers=headers,
            json={
                "order_id": str(order.id),
                "reservation_id": str(reservation.id),
                "payment_id": str(payment.id),
                "shipping_method": "standard",
            },
        )
        stale_pack = await client.post(
            f"/api/v1/shipments/{shipment.id}/pack",
            headers=headers,
            json={"version": shipment.version + 1, "packages": [_package()]},
        )
        pack = await client.post(
            f"/api/v1/shipments/{shipment.id}/pack",
            headers=headers,
            json={"version": shipment.version, "packages": [_package()]},
        )
        assert pack.status_code == 200, pack.text
        packed = ShipmentResponse.model_validate(pack.json())
        detail_response = await client.get(
            f"/api/v1/shipments/{shipment.id}", headers=headers
        )
        detail = ShipmentDetailResponse.model_validate(detail_response.json())
        list_response = await client.get("/api/v1/shipments", headers=headers)
        stale_ship = await client.post(
            f"/api/v1/shipments/{shipment.id}/ship",
            headers=headers,
            json={"version": packed.version + 1},
        )
        ship = await client.post(
            f"/api/v1/shipments/{shipment.id}/ship",
            headers=headers,
            json={"version": packed.version},
        )
        assert ship.status_code == 200, ship.text
        shipped = ShipmentResponse.model_validate(ship.json())
        inventory_after_ship_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inventory_after_ship = InventoryResponse.model_validate(
            inventory_after_ship_response.json()
        )
        stale_deliver = await client.post(
            f"/api/v1/shipments/{shipment.id}/deliver",
            headers=headers,
            json={"version": shipped.version + 1},
        )
        deliver = await client.post(
            f"/api/v1/shipments/{shipment.id}/deliver",
            headers=headers,
            json={"version": shipped.version},
        )
        assert deliver.status_code == 200, deliver.text
        delivered = ShipmentResponse.model_validate(deliver.json())
        tracking_response = await client.get(
            f"/api/v1/shipments/{shipment.id}/tracking", headers=headers
        )
        tracking = ShipmentTrackingResponse.model_validate(tracking_response.json())

        cancel_order, cancel_payment, cancel_reservation = await _reservation(
            client,
            headers,
            verified_store.id,
            product_variant.id,
            "shipment-pay-0002",
        )
        consume_cancel = await client.post(
            f"/api/v1/reservations/{cancel_reservation.id}/consume",
            headers=headers,
            json={"version": cancel_reservation.version},
        )
        assert consume_cancel.status_code == 200, consume_cancel.text
        cancel_create = await client.post(
            "/api/v1/shipments",
            headers=headers,
            json={
                "order_id": str(cancel_order.id),
                "reservation_id": str(cancel_reservation.id),
                "payment_id": str(cancel_payment.id),
                "shipping_method": "express",
            },
        )
        assert cancel_create.status_code == 201, cancel_create.text
        cancellable = ShipmentResponse.model_validate(cancel_create.json())
        cancel_pack = await client.post(
            f"/api/v1/shipments/{cancellable.id}/pack",
            headers=headers,
            json={"version": cancellable.version, "packages": [_package("PKG-2")]},
        )
        assert cancel_pack.status_code == 200, cancel_pack.text
        packed_cancel = ShipmentResponse.model_validate(cancel_pack.json())
        stale_cancel = await client.post(
            f"/api/v1/shipments/{cancellable.id}/cancel",
            headers=headers,
            json={"version": packed_cancel.version + 1},
        )
        cancel = await client.post(
            f"/api/v1/shipments/{cancellable.id}/cancel",
            headers=headers,
            json={"version": packed_cancel.version},
        )
        assert cancel.status_code == 200, cancel.text
        cancelled = ShipmentResponse.model_validate(cancel.json())
        hidden_cancelled = await client.get(
            f"/api/v1/shipments/{cancellable.id}", headers=headers
        )

    async with _authorized_client(
        async_client, second_identity, db_session, role="customer"
    ) as (client, second_headers):
        hidden = await client.get(
            f"/api/v1/shipments/{shipment.id}", headers=second_headers
        )

    assert premature.status_code == 409
    assert shipment.status is ShipmentStatus.READY_FOR_FULFILLMENT
    assert shipment.version == 2
    assert duplicate.status_code == 409
    assert stale_pack.status_code == 409
    assert packed.status is ShipmentStatus.PACKED
    assert packed.carrier == "null-carrier"
    assert packed.tracking_number is not None
    assert len(detail.packages) == 1
    assert detail.packages[0].weight == Decimal("1.250")
    page = ShipmentListResponse.model_validate(list_response.json())
    assert page.page.total == 1 and page.items[0].id == shipment.id
    assert stale_ship.status_code == 409
    assert shipped.status is ShipmentStatus.SHIPPED
    assert shipped.shipped_at is not None
    assert inventory_after_ship.quantity_on_hand == 8
    assert inventory_after_ship.quantity_reserved == 0
    assert inventory_after_ship.quantity_available == 8
    assert inventory_after_ship.version == inventory.version + 1
    assert stale_deliver.status_code == 409
    assert delivered.status is ShipmentStatus.DELIVERED
    assert delivered.delivered_at is not None
    assert [event.status for event in tracking.items] == [
        ShipmentStatus.CREATED,
        ShipmentStatus.READY_FOR_FULFILLMENT,
        ShipmentStatus.PACKED,
        ShipmentStatus.SHIPPED,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
    ]
    assert stale_cancel.status_code == 409
    assert cancelled.status is ShipmentStatus.CANCELLED
    assert hidden_cancelled.status_code == 404
    assert hidden.status_code == 404

    persisted = await db_session.get(ShipmentModel, shipment.id)
    assert persisted is not None and persisted.status is ShipmentStatus.DELIVERED
    cancelled_model = await db_session.get(ShipmentModel, cancellable.id)
    assert cancelled_model is not None and cancelled_model.deleted_at is not None
    events = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type == "shipment",
                EventOutboxModel.aggregate_id.in_([shipment.id, cancellable.id]),
            )
        )
    ).all()
    assert {event.event_name for event in events} == {
        "shipment.created",
        "shipment.packed",
        "shipment.shipped",
        "shipment.out_for_delivery",
        "shipment.delivered",
        "shipment.cancelled",
    }
    assert all(
        set(event.payload)
        == {
            "shipment_id",
            "order_id",
            "reservation_id",
            "payment_id",
            "customer_id",
            "store_id",
            "version",
            "timestamp",
        }
        for event in events
    )
    expected_increments = {
        "fashion_network_shipment_created_total": 2,
        "fashion_network_shipment_packed_total": 2,
        "fashion_network_shipment_shipped_total": 1,
        "fashion_network_shipment_delivered_total": 1,
        "fashion_network_shipment_cancelled_total": 1,
        "fashion_network_delivery_duration_seconds_count": 1,
    }
    for name, increment in expected_increments.items():
        assert _sample_value(name) == before[name] + increment


def _package(number: str = "PKG-1") -> dict[str, str]:
    return {
        "package_number": number,
        "weight": "1.250",
        "length": "20.000",
        "width": "15.000",
        "height": "10.000",
    }


def test_shipment_openapi_documents_routes_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/shipments", "shipment:create"),
        ("get", "/api/v1/shipments", "shipment:view"),
        ("get", "/api/v1/shipments/{shipment_id}", "shipment:view"),
        ("post", "/api/v1/shipments/{shipment_id}/pack", "shipment:update"),
        ("post", "/api/v1/shipments/{shipment_id}/ship", "shipment:ship"),
        ("post", "/api/v1/shipments/{shipment_id}/deliver", "shipment:deliver"),
        ("post", "/api/v1/shipments/{shipment_id}/cancel", "shipment:update"),
        ("get", "/api/v1/shipments/{shipment_id}/tracking", "shipment:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
