from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.inventory.api.schemas import (
    InventoryMovementListResponse,
    InventoryResponse,
    InventoryStockListResponse,
    RetailerOperationsSummaryResponse,
    RetailerOrderActivityListResponse,
    RetailerShipmentActivityListResponse,
)
from app.modules.inventory.domain import InventoryMovementType
from app.modules.inventory.infrastructure.models import InventoryMovementModel
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.shipments.api.schemas import ShipmentResponse
from app.modules.stores.application.membership_schemas import (
    StoreMembershipInvitation,
)
from app.modules.stores.domain import Store, StoreMembershipRole
from tests.test_order import _authorized_client, _second_identity
from tests.test_reservation import _create_captured_order
from tests.test_shipment import _package, _reservation
from tests.test_store_membership import RecordingPublisher, _service

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


async def _inventory(
    client: AsyncClient,
    headers: dict[str, str],
    variant_id: object,
    *,
    quantity: int = 12,
    reserved: int = 0,
    threshold: int = 4,
) -> InventoryResponse:
    response = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "variant_id": str(variant_id),
            "quantity_on_hand": quantity,
            "quantity_reserved": reserved,
            "low_stock_threshold": threshold,
        },
    )
    assert response.status_code == 201, response.text
    return InventoryResponse.model_validate(response.json())


async def _active_price(
    client: AsyncClient,
    headers: dict[str, str],
    store: Store,
    product: Product,
    variant: ProductVariant,
) -> ProductPriceResponse:
    response = await client.post(
        "/api/v1/prices",
        headers=headers,
        json={
            "store_id": str(store.id),
            "product_id": str(product.id),
            "variant_id": str(variant.id),
            "currency_code": "INR",
            "base_price": "100.0000",
            "tax_class": "standard",
            "status": "draft",
        },
    )
    assert response.status_code == 201, response.text
    draft = ProductPriceResponse.model_validate(response.json())
    activation = await client.patch(
        f"/api/v1/prices/{draft.id}",
        headers=headers,
        json={"status": "active", "version": draft.version},
    )
    assert activation.status_code == 200, activation.text
    return ProductPriceResponse.model_validate(activation.json())


async def test_adjust_reconcile_history_thresholds_and_outbox(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    reference_id = uuid4()
    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
    ) as (client, headers):
        inventory = await _inventory(client, headers, product_variant.id, reserved=3)
        adjusted_response = await client.post(
            f"/api/v1/inventory/{inventory.id}/adjust",
            headers=headers,
            json={
                "quantity_delta": -5,
                "movement_type": "damage",
                "reason": "Damaged during shelf inspection",
                "version": inventory.version,
                "source": "cycle_count",
                "reference_id": str(reference_id),
            },
        )
        stale_response = await client.post(
            f"/api/v1/inventory/{inventory.id}/adjust",
            headers=headers,
            json={
                "quantity_delta": 1,
                "movement_type": "found",
                "reason": "Stale concurrent adjustment",
                "version": inventory.version,
            },
        )
        adjusted = InventoryResponse.model_validate(adjusted_response.json())
        low_response = await client.get(
            "/api/v1/inventory/low-stock",
            headers=headers,
            params={"store_id": str(verified_store.id)},
        )
        filtered_history_response = await client.get(
            f"/api/v1/inventory/{inventory.id}/movements",
            headers=headers,
            params={
                "movement_type": "damage",
                "source": "cycle_count",
                "reference_id": str(reference_id),
                "limit": 1,
            },
        )
        reconcile_response = await client.post(
            f"/api/v1/inventory/{inventory.id}/reconcile",
            headers=headers,
            json={
                "physical_count": 3,
                "reason": "Completed physical stock count",
                "version": adjusted.version,
            },
        )
        reconciled = InventoryResponse.model_validate(reconcile_response.json())
        out_response = await client.get(
            "/api/v1/inventory/out-of-stock",
            headers=headers,
            params={"store_id": str(verified_store.id)},
        )
        history_response = await client.get(
            "/api/v1/inventory/movements",
            headers=headers,
            params={"inventory_id": str(inventory.id), "limit": 2},
        )

    assert adjusted_response.status_code == 200
    assert adjusted.quantity_on_hand == 7
    assert adjusted.quantity_available == 4
    assert adjusted.version == 2
    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "conflict"

    low = InventoryStockListResponse.model_validate(low_response.json())
    assert [item.inventory.id for item in low.items] == [inventory.id]
    assert low.items[0].effective_available == 4
    assert low.items[0].classification.value == "low_stock"

    filtered = InventoryMovementListResponse.model_validate(
        filtered_history_response.json()
    )
    assert filtered.page.total == 1
    assert filtered.items[0].reference_id == reference_id
    assert filtered.items[0].actor_id == authenticated_identity.user.id
    assert filtered.items[0].previous_on_hand == 12
    assert filtered.items[0].new_on_hand == 7
    assert filtered.items[0].reservation_quantity == 3

    assert reconciled.quantity_on_hand == 3
    assert reconciled.quantity_available == 0
    assert reconciled.status.value == "out_of_stock"
    assert reconciled.version == 3
    out = InventoryStockListResponse.model_validate(out_response.json())
    assert [item.inventory.id for item in out.items] == [inventory.id]

    history = InventoryMovementListResponse.model_validate(history_response.json())
    assert history.page.total == 3
    assert history.page.has_more
    assert [movement.movement_type for movement in history.items] == [
        InventoryMovementType.RECONCILIATION,
        InventoryMovementType.DAMAGE,
    ]
    persisted = (
        await db_session.scalars(
            select(InventoryMovementModel)
            .where(InventoryMovementModel.inventory_id == inventory.id)
            .order_by(InventoryMovementModel.created_at, InventoryMovementModel.id)
        )
    ).all()
    assert len(persisted) == 3
    assert persisted[-1].actor_id == authenticated_identity.user.id
    assert persisted[-1].reason == "Completed physical stock count"
    events = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_id == inventory.id,
                EventOutboxModel.event_name.in_(
                    (
                        "inventory.adjusted",
                        "inventory.reconciled",
                        "inventory.low_stock",
                        "inventory.out_of_stock",
                    )
                ),
            )
        )
    ).all()
    assert {event.event_name for event in events} == {
        "inventory.adjusted",
        "inventory.reconciled",
        "inventory.low_stock",
        "inventory.out_of_stock",
    }
    assert all(
        set(event.payload)
        == {
            "inventory_id",
            "variant_id",
            "product_id",
            "catalog_id",
            "store_id",
            "version",
        }
        for event in events
    )


async def test_reconciliation_protects_active_reservations(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
    ) as (client, headers):
        inventory = await _inventory(client, headers, product_variant.id, quantity=10)
        await _active_price(client, headers, verified_store, product, product_variant)
        order, payment = await _create_captured_order(
            client,
            headers,
            store_id=verified_store.id,
            variant_id=product_variant.id,
            quantity=6,
            key="retailer-operations-reservation",
        )
        reservation_response = await client.post(
            "/api/v1/reservations",
            headers=headers,
            json={"order_id": str(order.id), "payment_id": str(payment.id)},
        )
        assert reservation_response.status_code == 201, reservation_response.text
        conflict = await client.post(
            f"/api/v1/inventory/{inventory.id}/reconcile",
            headers=headers,
            json={
                "physical_count": 5,
                "reason": "Count is below active customer holds",
                "version": inventory.version,
            },
        )
        detail = await client.get(f"/api/v1/inventory/{inventory.id}", headers=headers)

    assert conflict.status_code == 409
    assert "Reservations" in conflict.json()["detail"]
    unchanged = InventoryResponse.model_validate(detail.json())
    assert unchanged.quantity_on_hand == 10
    assert unchanged.version == inventory.version


async def test_operational_summary_order_and_shipment_queries(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
    ) as (client, headers):
        await _inventory(client, headers, product_variant.id, quantity=10)
        await _active_price(client, headers, verified_store, product, product_variant)
        order, payment, reservation = await _reservation(
            client,
            headers,
            verified_store.id,
            product_variant.id,
            "retailer-operations-shipment",
        )
        consume = await client.post(
            f"/api/v1/reservations/{reservation.id}/consume",
            headers=headers,
            json={"version": reservation.version},
        )
        assert consume.status_code == 200, consume.text
        shipment_response = await client.post(
            "/api/v1/shipments",
            headers=headers,
            json={
                "order_id": str(order.id),
                "reservation_id": str(reservation.id),
                "payment_id": str(payment.id),
                "shipping_method": "standard",
            },
        )
        assert shipment_response.status_code == 201, shipment_response.text
        shipment = ShipmentResponse.model_validate(shipment_response.json())
        pack = await client.post(
            f"/api/v1/shipments/{shipment.id}/pack",
            headers=headers,
            json={"version": shipment.version, "packages": [_package("OPS-1")]},
        )
        assert pack.status_code == 200, pack.text
        summary_response = await client.get(
            "/api/v1/retailer/operations/summary",
            headers=headers,
            params={"store_id": str(verified_store.id)},
        )
        orders_response = await client.get(
            "/api/v1/retailer/operations/orders",
            headers=headers,
            params={"store_id": str(verified_store.id), "limit": 1},
        )
        shipments_response = await client.get(
            "/api/v1/retailer/operations/shipments",
            headers=headers,
            params={
                "store_id": str(verified_store.id),
                "status": "packed",
                "limit": 1,
            },
        )

    assert summary_response.status_code == 200
    summary = RetailerOperationsSummaryResponse.model_validate(summary_response.json())
    assert summary.active_products == 1
    assert summary.active_variants == 1
    assert summary.in_stock_variants == 1
    assert summary.shipments_pending_fulfillment == 1
    assert summary.recent_movements
    orders = RetailerOrderActivityListResponse.model_validate(orders_response.json())
    assert orders.page.total == 1
    assert orders.items[0].id == order.id
    assert orders.items[0].shipment_status == "packed"
    shipments = RetailerShipmentActivityListResponse.model_validate(
        shipments_response.json()
    )
    assert shipments.page.total == 1
    assert shipments.items[0].id == shipment.id
    assert shipments.items[0].status == "packed"


async def test_store_isolation_staff_access_and_authorization(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    staff = await _second_identity(db_session)
    outsider = await _second_identity(db_session)
    customer = await _second_identity(db_session)
    membership_service = _service(db_session, RecordingPublisher())
    invitation = await membership_service.invite(
        verified_store.id,
        authenticated_identity.user.id,
        StoreMembershipInvitation(staff.user.id, StoreMembershipRole.STAFF),
    )
    await membership_service.accept(
        verified_store.id, invitation.id, staff.user.id, invitation.version
    )
    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="store_owner"
    ) as (client, owner_headers):
        inventory = await _inventory(client, owner_headers, product_variant.id)

    async with _authorized_client(
        async_client, staff, db_session, role="store_staff"
    ) as (client, staff_headers):
        staff_product = await client.get(
            f"/api/v1/products/{product.id}", headers=staff_headers
        )
        staff_variants = await client.get(
            f"/api/v1/products/{product.id}/variants", headers=staff_headers
        )
        staff_summary = await client.get(
            "/api/v1/retailer/operations/summary",
            headers=staff_headers,
            params={"store_id": str(verified_store.id)},
        )
    async with _authorized_client(
        async_client, outsider, db_session, role="store_owner"
    ) as (client, outsider_headers):
        hidden = await client.get(
            f"/api/v1/inventory/{inventory.id}/movements",
            headers=outsider_headers,
        )
        hidden_summary = await client.get(
            "/api/v1/retailer/operations/summary",
            headers=outsider_headers,
            params={"store_id": str(verified_store.id)},
        )
    async with _authorized_client(async_client, customer, db_session, role=None) as (
        client,
        customer_headers,
    ):
        forbidden = await client.post(
            f"/api/v1/inventory/{inventory.id}/adjust",
            headers=customer_headers,
            json={
                "quantity_delta": 1,
                "movement_type": "found",
                "reason": "Unauthorized operation",
                "version": inventory.version,
            },
        )

    assert staff_product.status_code == 200
    assert staff_variants.status_code == 200
    assert staff_summary.status_code == 200
    assert hidden.status_code == 404
    assert hidden_summary.status_code == 404
    assert forbidden.status_code == 403


def test_retailer_operations_openapi_permissions(application: FastAPI) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/inventory/{inventory_id}/adjust", "inventory:update"),
        ("post", "/api/v1/inventory/{inventory_id}/reconcile", "inventory:update"),
        ("get", "/api/v1/inventory/{inventory_id}/movements", "inventory:view"),
        ("get", "/api/v1/inventory/movements", "inventory:view"),
        ("get", "/api/v1/inventory/low-stock", "inventory:view"),
        ("get", "/api/v1/inventory/out-of-stock", "inventory:view"),
        ("get", "/api/v1/retailer/operations/summary", "inventory:view"),
        ("get", "/api/v1/retailer/operations/orders", "inventory:view"),
        ("get", "/api/v1/retailer/operations/shipments", "inventory:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
