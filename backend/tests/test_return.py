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
from app.modules.orders.api.schemas import OrderResponse, OrderSummaryResponse
from app.modules.payments.api.schemas import PaymentIntentResponse
from app.modules.pricing.api.schemas import ProductPriceResponse
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.reservations.api.schemas import ReservationResponse
from app.modules.returns.api.schemas import (
    RefundDetailResponse,
    RefundListResponse,
    RefundResponse,
    RefundStatusResponse,
    ReturnDetailResponse,
    ReturnListResponse,
    ReturnResponse,
    ReturnSummaryResponse,
)
from app.modules.returns.domain import (
    InventoryDisposition,
    RefundCompleted,
    RefundCreated,
    RefundFailed,
    RefundStatus,
    ReturnApproved,
    ReturnCancelled,
    ReturnInspected,
    ReturnReceived,
    ReturnRejected,
    ReturnRequested,
    ReturnStatus,
)
from app.modules.returns.infrastructure.models import (
    RefundModel,
    RefundTransactionModel,
    ReturnItemModel,
    ReturnModel,
)
from app.modules.shipments.api.schemas import ShipmentResponse
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


def test_return_domain_events_and_persistence_contracts() -> None:
    return_names = {
        event_type(
            return_id=UUID(int=1),
            order_id=UUID(int=2),
            customer_id=UUID(int=3),
            store_id=UUID(int=4),
            version=1,
        ).event_name
        for event_type in (
            ReturnRequested,
            ReturnApproved,
            ReturnReceived,
            ReturnInspected,
            ReturnRejected,
            ReturnCancelled,
        )
    }
    refund_names = {
        event_type(
            refund_id=UUID(int=1),
            return_id=UUID(int=2),
            payment_id=UUID(int=3),
            customer_id=UUID(int=4),
            store_id=UUID(int=5),
            version=1,
        ).event_name
        for event_type in (RefundCreated, RefundCompleted, RefundFailed)
    }
    assert return_names == {
        "return.requested",
        "return.approved",
        "return.received",
        "return.inspected",
        "return.rejected",
        "return.cancelled",
    }
    assert refund_names == {"refund.created", "refund.completed", "refund.failed"}
    return_table = cast(Table, ReturnModel.__table__)
    item_table = cast(Table, ReturnItemModel.__table__)
    refund_table = cast(Table, RefundModel.__table__)
    transaction_table = cast(Table, RefundTransactionModel.__table__)
    assert "ix_returns_customer" in {index.name for index in return_table.indexes}
    assert "uq_return_items_order_item" in {
        value.name for value in item_table.constraints
    }
    assert "uq_refunds_return" in {value.name for value in refund_table.constraints}
    assert "uq_refund_transactions_provider_id" in {
        value.name for value in transaction_table.constraints
    }


async def _delivered_chain(
    client: AsyncClient,
    headers: dict[str, str],
    store_id: UUID,
    variant_id: UUID,
    key: str,
    *,
    quantity: int,
    probe_undelivered: bool = False,
) -> tuple[
    OrderResponse,
    PaymentIntentResponse,
    ShipmentResponse,
    OrderSummaryResponse,
    int | None,
]:
    order, payment = await _create_captured_order(
        client,
        headers,
        store_id=store_id,
        variant_id=variant_id,
        quantity=2,
        key=key,
    )
    reservation_response = await client.post(
        "/api/v1/reservations",
        headers=headers,
        json={"order_id": str(order.id), "payment_id": str(payment.id)},
    )
    assert reservation_response.status_code == 201, reservation_response.text
    reservation = ReservationResponse.model_validate(reservation_response.json())
    consume = await client.post(
        f"/api/v1/reservations/{reservation.id}/consume",
        headers=headers,
        json={"version": reservation.version},
    )
    assert consume.status_code == 200, consume.text
    summary_response = await client.get(
        f"/api/v1/orders/{order.id}/summary", headers=headers
    )
    assert summary_response.status_code == 200, summary_response.text
    summary = OrderSummaryResponse.model_validate(summary_response.json())
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
    probe_status = None
    if probe_undelivered:
        probe = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(order.id),
                "shipment_id": str(shipment.id),
                "payment_id": str(payment.id),
                "reason": "Not delivered yet",
                "items": [
                    {
                        "order_item_id": str(summary.items[0].id),
                        "quantity": quantity,
                    }
                ],
            },
        )
        probe_status = probe.status_code
    pack = await client.post(
        f"/api/v1/shipments/{shipment.id}/pack",
        headers=headers,
        json={"version": shipment.version, "packages": [_package(key[-4:])]},
    )
    assert pack.status_code == 200, pack.text
    packed = ShipmentResponse.model_validate(pack.json())
    ship = await client.post(
        f"/api/v1/shipments/{shipment.id}/ship",
        headers=headers,
        json={"version": packed.version},
    )
    assert ship.status_code == 200, ship.text
    shipped = ShipmentResponse.model_validate(ship.json())
    deliver = await client.post(
        f"/api/v1/shipments/{shipment.id}/deliver",
        headers=headers,
        json={"version": shipped.version},
    )
    assert deliver.status_code == 200, deliver.text
    return (
        order,
        payment,
        ShipmentResponse.model_validate(deliver.json()),
        summary,
        probe_status,
    )


def _package(number: str) -> dict[str, str]:
    return {
        "package_number": number,
        "weight": "1.250",
        "length": "20.000",
        "width": "15.000",
        "height": "10.000",
    }


async def test_return_refund_production_stack_lifecycle_ownership_and_persistence(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    metric_names = (
        "fashion_network_return_created_total",
        "fashion_network_return_received_total",
        "fashion_network_return_refunded_total",
        "fashion_network_return_rejected_total",
        "fashion_network_refund_completed_total",
        "fashion_network_refund_failed_total",
        "fashion_network_refund_duration_seconds_count",
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
                "quantity_on_hand": 12,
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

        order, payment, shipment, summary, undelivered_status = await _delivered_chain(
            client,
            headers,
            verified_store.id,
            product_variant.id,
            "return-payment-0001",
            quantity=1,
            probe_undelivered=True,
        )
        order_item = summary.items[0]
        excessive = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(order.id),
                "shipment_id": str(shipment.id),
                "payment_id": str(payment.id),
                "reason": "Too many",
                "items": [{"order_item_id": str(order_item.id), "quantity": 3}],
            },
        )
        create = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(order.id),
                "shipment_id": str(shipment.id),
                "payment_id": str(payment.id),
                "reason": "  Wrong   size  ",
                "items": [{"order_item_id": str(order_item.id), "quantity": 1}],
            },
        )
        assert create.status_code == 201, create.text
        requested = ReturnResponse.model_validate(create.json())
        stale_update = await client.patch(
            f"/api/v1/returns/{requested.id}",
            headers=headers,
            json={"reason": "Updated reason", "version": requested.version + 1},
        )
        update = await client.patch(
            f"/api/v1/returns/{requested.id}",
            headers=headers,
            json={"reason": "Updated reason", "version": requested.version},
        )
        assert update.status_code == 200, update.text
        updated = ReturnResponse.model_validate(update.json())
        cumulative = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(order.id),
                "shipment_id": str(shipment.id),
                "payment_id": str(payment.id),
                "reason": "Remaining quantity overflow",
                "items": [{"order_item_id": str(order_item.id), "quantity": 2}],
            },
        )
        detail_response = await client.get(
            f"/api/v1/returns/{requested.id}", headers=headers
        )
        detail = ReturnDetailResponse.model_validate(detail_response.json())
        list_response = await client.get("/api/v1/returns", headers=headers)
        summary_response = await client.get(
            f"/api/v1/returns/{requested.id}/summary", headers=headers
        )
        return_summary = ReturnSummaryResponse.model_validate(summary_response.json())
        stale_approve = await client.post(
            f"/api/v1/returns/{requested.id}/approve",
            headers=headers,
            json={"version": updated.version + 1},
        )
        approve = await client.post(
            f"/api/v1/returns/{requested.id}/approve",
            headers=headers,
            json={"version": updated.version},
        )
        assert approve.status_code == 200, approve.text
        approved = ReturnResponse.model_validate(approve.json())
        receive = await client.post(
            f"/api/v1/returns/{requested.id}/receive",
            headers=headers,
            json={"version": approved.version},
        )
        assert receive.status_code == 200, receive.text
        received = ReturnResponse.model_validate(receive.json())
        inventory_before_inspection = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inspect = await client.post(
            f"/api/v1/returns/{requested.id}/inspect",
            headers=headers,
            json={
                "version": received.version,
                "dispositions": [
                    {
                        "return_item_id": str(detail.items[0].id),
                        "disposition": "restock",
                    }
                ],
            },
        )
        assert inspect.status_code == 200, inspect.text
        inspected = ReturnResponse.model_validate(inspect.json())
        inventory_after_inspection_response = await client.get(
            f"/api/v1/inventory/{inventory.id}", headers=headers
        )
        inventory_after_inspection = InventoryResponse.model_validate(
            inventory_after_inspection_response.json()
        )
        refund_create = await client.post(
            "/api/v1/refunds",
            headers=headers,
            json={"return_id": str(requested.id)},
        )
        assert refund_create.status_code == 201, refund_create.text
        refund = RefundResponse.model_validate(refund_create.json())
        duplicate_refund = await client.post(
            "/api/v1/refunds",
            headers=headers,
            json={"return_id": str(requested.id)},
        )
        stale_process = await client.post(
            f"/api/v1/refunds/{refund.id}/process",
            headers=headers,
            json={"version": refund.version + 1},
        )
        process = await client.post(
            f"/api/v1/refunds/{refund.id}/process",
            headers=headers,
            json={"version": refund.version},
        )
        assert process.status_code == 200, process.text
        completed = RefundResponse.model_validate(process.json())
        refund_detail_response = await client.get(
            f"/api/v1/refunds/{refund.id}", headers=headers
        )
        refund_detail = RefundDetailResponse.model_validate(
            refund_detail_response.json()
        )
        refund_list_response = await client.get("/api/v1/refunds", headers=headers)
        refund_status_response = await client.get(
            f"/api/v1/refunds/{refund.id}/status", headers=headers
        )
        refund_status = RefundStatusResponse.model_validate(
            refund_status_response.json()
        )
        refunded_return_response = await client.get(
            f"/api/v1/returns/{requested.id}", headers=headers
        )
        refunded_return = ReturnDetailResponse.model_validate(
            refunded_return_response.json()
        )

        reject_order, reject_payment, reject_shipment, reject_summary, _ = (
            await _delivered_chain(
                client,
                headers,
                verified_store.id,
                product_variant.id,
                "return-payment-0002",
                quantity=1,
            )
        )
        reject_create = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(reject_order.id),
                "shipment_id": str(reject_shipment.id),
                "payment_id": str(reject_payment.id),
                "reason": "Reject path",
                "items": [
                    {"order_item_id": str(reject_summary.items[0].id), "quantity": 1}
                ],
            },
        )
        assert reject_create.status_code == 201, reject_create.text
        rejectable = ReturnResponse.model_validate(reject_create.json())
        reject = await client.post(
            f"/api/v1/returns/{rejectable.id}/reject",
            headers=headers,
            json={"version": rejectable.version},
        )
        assert reject.status_code == 200, reject.text
        rejected = ReturnResponse.model_validate(reject.json())
        hidden_rejected = await client.get(
            f"/api/v1/returns/{rejectable.id}", headers=headers
        )

        cancel_order, cancel_payment, cancel_shipment, cancel_summary, _ = (
            await _delivered_chain(
                client,
                headers,
                verified_store.id,
                product_variant.id,
                "return-payment-0003",
                quantity=1,
            )
        )
        cancel_create = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "order_id": str(cancel_order.id),
                "shipment_id": str(cancel_shipment.id),
                "payment_id": str(cancel_payment.id),
                "reason": "Cancel path",
                "items": [
                    {"order_item_id": str(cancel_summary.items[0].id), "quantity": 1}
                ],
            },
        )
        assert cancel_create.status_code == 201, cancel_create.text
        cancellable = ReturnResponse.model_validate(cancel_create.json())
        cancel_approve = await client.post(
            f"/api/v1/returns/{cancellable.id}/approve",
            headers=headers,
            json={"version": cancellable.version},
        )
        assert cancel_approve.status_code == 200, cancel_approve.text
        approved_cancel = ReturnResponse.model_validate(cancel_approve.json())
        cancel = await client.post(
            f"/api/v1/returns/{cancellable.id}/cancel",
            headers=headers,
            json={"version": approved_cancel.version},
        )
        assert cancel.status_code == 200, cancel.text
        cancelled = ReturnResponse.model_validate(cancel.json())

    async with _authorized_client(
        async_client, second_identity, db_session, role="customer"
    ) as (client, second_headers):
        hidden_return = await client.get(
            f"/api/v1/returns/{requested.id}", headers=second_headers
        )
        hidden_refund = await client.get(
            f"/api/v1/refunds/{refund.id}", headers=second_headers
        )

    assert undelivered_status == 409
    assert excessive.status_code == 409
    assert requested.status is ReturnStatus.REQUESTED
    assert requested.reason == "Wrong size"
    assert stale_update.status_code == 409
    assert cumulative.status_code == 409
    assert len(detail.items) == 1
    assert detail.items[0].disposition is InventoryDisposition.INSPECTION_REQUIRED
    return_page = ReturnListResponse.model_validate(list_response.json())
    assert return_page.page.total == 1
    assert return_summary.item_quantity == 1
    assert return_summary.refundable_amount == Decimal("100.0000")
    assert stale_approve.status_code == 409
    assert received.status is ReturnStatus.RECEIVED
    assert inspected.status is ReturnStatus.REFUND_PENDING
    inventory_before = InventoryResponse.model_validate(
        inventory_before_inspection.json()
    )
    assert inventory_after_inspection == inventory_before
    assert refund.status is RefundStatus.PENDING
    assert refund.amount == Decimal("100.0000")
    assert duplicate_refund.status_code == 409
    assert stale_process.status_code == 409
    assert completed.status is RefundStatus.COMPLETED
    assert completed.completed_at is not None
    assert [value.status for value in refund_detail.transactions] == [
        RefundStatus.PENDING,
        RefundStatus.PROCESSING,
        RefundStatus.COMPLETED,
    ]
    refund_page = RefundListResponse.model_validate(refund_list_response.json())
    assert refund_page.page.total == 1
    assert refund_status.status is RefundStatus.COMPLETED
    assert refunded_return.status is ReturnStatus.REFUNDED
    assert rejected.status is ReturnStatus.REJECTED
    assert hidden_rejected.status_code == 404
    assert cancelled.status is ReturnStatus.CANCELLED
    assert hidden_return.status_code == 404
    assert hidden_refund.status_code == 404

    persisted = await db_session.get(ReturnModel, requested.id)
    assert persisted is not None and persisted.status is ReturnStatus.REFUNDED
    persisted_refund = await db_session.get(RefundModel, refund.id)
    assert persisted_refund is not None
    assert persisted_refund.status is RefundStatus.COMPLETED
    rejected_model = await db_session.get(ReturnModel, rejectable.id)
    assert rejected_model is not None and rejected_model.deleted_at is not None
    cancelled_model = await db_session.get(ReturnModel, cancellable.id)
    assert cancelled_model is not None and cancelled_model.deleted_at is not None
    outbox = (
        await db_session.scalars(
            select(EventOutboxModel).where(
                EventOutboxModel.aggregate_type.in_(["return", "refund"]),
                EventOutboxModel.aggregate_id.in_(
                    [requested.id, refund.id, rejectable.id, cancellable.id]
                ),
            )
        )
    ).all()
    assert {event.event_name for event in outbox} == {
        "return.requested",
        "return.approved",
        "return.received",
        "return.inspected",
        "return.rejected",
        "return.cancelled",
        "refund.created",
        "refund.completed",
    }
    assert all(
        "amount" not in event.payload and "currency" not in event.payload
        for event in outbox
    )
    increments = {
        "fashion_network_return_created_total": 3,
        "fashion_network_return_received_total": 1,
        "fashion_network_return_refunded_total": 1,
        "fashion_network_return_rejected_total": 1,
        "fashion_network_refund_completed_total": 1,
        "fashion_network_refund_failed_total": 0,
        "fashion_network_refund_duration_seconds_count": 1,
    }
    for name, increment in increments.items():
        assert _sample_value(name) == before[name] + increment


def test_return_refund_openapi_documents_permissions(application: FastAPI) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/returns", "return:create"),
        ("get", "/api/v1/returns", "return:view"),
        ("get", "/api/v1/returns/{return_id}", "return:view"),
        ("patch", "/api/v1/returns/{return_id}", "return:update"),
        ("post", "/api/v1/returns/{return_id}/approve", "return:approve"),
        ("post", "/api/v1/returns/{return_id}/receive", "return:receive"),
        ("post", "/api/v1/returns/{return_id}/inspect", "return:inspect"),
        ("post", "/api/v1/returns/{return_id}/reject", "return:reject"),
        ("post", "/api/v1/returns/{return_id}/cancel", "return:update"),
        ("get", "/api/v1/returns/{return_id}/summary", "return:view"),
        ("post", "/api/v1/refunds", "refund:create"),
        ("get", "/api/v1/refunds", "refund:view"),
        ("get", "/api/v1/refunds/{refund_id}", "refund:view"),
        ("post", "/api/v1/refunds/{refund_id}/process", "refund:process"),
        ("get", "/api/v1/refunds/{refund_id}/status", "refund:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
