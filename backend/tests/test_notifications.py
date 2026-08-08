from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from prometheus_client import generate_latest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.notifications.application.dispatchers import NotificationDispatcher
from app.modules.notifications.domain import (
    NotificationChannel,
    NotificationCreated,
    NotificationFailed,
    NotificationRead,
    NotificationSent,
    NotificationStatus,
)
from app.modules.notifications.gateways import NullNotificationGateway
from app.modules.notifications.infrastructure.models import (
    NotificationDeliveryModel,
    NotificationFailureModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationTemplateModel,
)
from app.modules.notifications.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyNotificationOutboxRepository,
    SqlAlchemyNotificationRepository,
    SqlAlchemyPreferenceRepository,
    SqlAlchemyTemplateRepository,
)
from app.modules.notifications.templates import render_template
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.promotions.application.services import PromotionOutboxService
from app.modules.promotions.domain import PromotionApplied
from app.modules.promotions.infrastructure.repositories import (
    SqlAlchemyPromotionOutboxRepository,
)
from app.modules.stores.domain import Store
from tests.test_order import _authorized_client, _second_identity

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
)


def _metric(name: str, channel: str) -> float:
    prefix = f'{name}{{channel="{channel}"}} '
    return next(
        (
            float(line.removeprefix(prefix))
            for line in generate_latest().decode().splitlines()
            if line.startswith(prefix)
        ),
        0.0,
    )


def _dispatcher(
    session: AsyncSession, gateway: NullNotificationGateway
) -> NotificationDispatcher:
    return NotificationDispatcher(
        SqlAlchemyNotificationRepository(session),
        SqlAlchemyPreferenceRepository(session),
        SqlAlchemyTemplateRepository(session),
        SqlAlchemyDeliveryRepository(session),
        SqlAlchemyNotificationOutboxRepository(session),
        gateway,
        max_retries=2,
        retry_base_seconds=1,
    )


async def test_plain_text_renderer_and_null_gateway_contract() -> None:
    assert (
        render_template("Order $order_id", {"order_id": UUID(int=1)})
        == "Order 00000000-0000-0000-0000-000000000001"
    )
    gateway = NullNotificationGateway()
    email = await gateway.send_email("customer", "Subject", "Body", "email-key")
    sms = await gateway.send_sms("customer", "Body", "sms-key")
    push = await gateway.send_push("customer", "Subject", "Body", "push-key")
    in_app = await gateway.send_in_app("customer", "Subject", "Body", "app-key")
    assert all(result.delivered for result in (email, sms, push, in_app))
    assert email == await gateway.send_email("customer", "Subject", "Body", "email-key")


def test_notification_events_models_and_openapi(application: FastAPI) -> None:
    expected_names = {
        NotificationCreated: "notification.created",
        NotificationSent: "notification.sent",
        NotificationFailed: "notification.failed",
        NotificationRead: "notification.read",
    }
    for event_type, event_name in expected_names.items():
        event = event_type(
            notification_id=UUID(int=1),
            customer_id=UUID(int=2),
            store_id=UUID(int=3),
            version=1,
        )
        assert event.event_name == event_name
        assert set(event.payload) == {
            "notification_id",
            "customer_id",
            "store_id",
            "version",
            "timestamp",
        }
    table = cast(Table, NotificationModel.__table__)
    assert "uq_notifications_source_customer_channel" in {
        constraint.name for constraint in table.constraints
    }
    assert {
        "ix_notifications_customer_status",
        "ix_notifications_retry",
        "ix_notifications_source_event",
    } <= {index.name for index in table.indexes}
    schema = application.openapi()
    expected_routes = {
        ("get", "/api/v1/notifications", "notification:view"),
        ("get", "/api/v1/notifications/preferences", "notification:preferences"),
        (
            "patch",
            "/api/v1/notifications/preferences",
            "notification:preferences",
        ),
        ("post", "/api/v1/notifications/test", "notification:test"),
        (
            "get",
            "/api/v1/notifications/{notification_id}",
            "notification:view",
        ),
        (
            "patch",
            "/api/v1/notifications/{notification_id}/read",
            "notification:update",
        ),
    }
    for method, path, permission in expected_routes:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]


async def test_notification_production_stack_and_delivery_contract(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    db_session: AsyncSession,
) -> None:
    second_identity = await _second_identity(db_session)
    created_before = _metric("fashion_network_notifications_created_total", "email")
    sent_before = _metric("fashion_network_notifications_sent_total", "email")
    event = PromotionApplied(
        promotion_id=uuid7(),
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=1,
    )
    await PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(db_session)).write(
        event
    )
    dispatcher = _dispatcher(db_session, NullNotificationGateway())
    assert await dispatcher.dispatch_pending() == 2
    assert await dispatcher.dispatch_pending() == 0

    notifications = (
        await db_session.scalars(
            select(NotificationModel)
            .where(NotificationModel.source_event_id == event.event_id)
            .order_by(NotificationModel.channel)
        )
    ).all()
    assert len(notifications) == 4
    delivered = [
        value for value in notifications if value.status == NotificationStatus.DELIVERED
    ]
    cancelled = [
        value for value in notifications if value.status == NotificationStatus.CANCELLED
    ]
    assert {value.channel for value in delivered} == {
        NotificationChannel.EMAIL,
        NotificationChannel.IN_APP,
    }
    assert {value.channel for value in cancelled} == {
        NotificationChannel.SMS,
        NotificationChannel.PUSH,
    }
    assert all(value.deleted_at is not None for value in cancelled)
    assert (
        await db_session.scalar(
            select(func.count(NotificationDeliveryModel.id)).where(
                NotificationDeliveryModel.notification_id.in_(
                    [value.id for value in delivered]
                )
            )
        )
        == 2
    )
    outbox = await db_session.get(EventOutboxModel, event.event_id)
    assert outbox is not None and outbox.status.value == "published"
    assert (
        _metric("fashion_network_notifications_created_total", "email")
        == created_before + 1
    )
    assert (
        _metric("fashion_network_notifications_sent_total", "email") == sent_before + 1
    )

    async with _authorized_client(
        async_client, authenticated_identity, db_session, role="admin"
    ) as (client, headers):
        listing = await client.get("/api/v1/notifications", headers=headers)
        assert listing.status_code == 200, listing.text
        payload = listing.json()
        assert payload["page"]["total"] == 2
        notification_id = payload["items"][0]["id"]
        version = payload["items"][0]["version"]
        detail = await client.get(
            f"/api/v1/notifications/{notification_id}", headers=headers
        )
        assert detail.status_code == 200
        read = await client.patch(
            f"/api/v1/notifications/{notification_id}/read",
            headers=headers,
            json={"version": version},
        )
        assert read.status_code == 200 and read.json()["read_at"] is not None
        stale = await client.patch(
            f"/api/v1/notifications/{notification_id}/read",
            headers=headers,
            json={"version": version},
        )
        assert stale.status_code == 409
        preference = await client.get(
            "/api/v1/notifications/preferences", headers=headers
        )
        assert preference.status_code == 200
        preference_version = preference.json()["version"]
        updated = await client.patch(
            "/api/v1/notifications/preferences",
            headers=headers,
            json={
                "version": preference_version,
                "sms_enabled": True,
                "marketing_opt_in": False,
            },
        )
        assert updated.status_code == 200 and updated.json()["sms_enabled"] is True
        stale_preference = await client.patch(
            "/api/v1/notifications/preferences",
            headers=headers,
            json={"version": preference_version, "push_enabled": True},
        )
        assert stale_preference.status_code == 409
        test_response = await client.post(
            "/api/v1/notifications/test",
            headers=headers,
            json={
                "channel": "in_app",
                "subject": "System test",
                "body": "Delivery path operational",
            },
        )
        assert test_response.status_code == 201, test_response.text
        assert test_response.json()["status"] == "delivered"

    async with _authorized_client(
        async_client, second_identity, db_session, role="customer"
    ) as (client, headers):
        isolated = await client.get("/api/v1/notifications", headers=headers)
        assert isolated.status_code == 200
        assert isolated.json()["page"]["total"] == 0
        hidden = await client.get(
            f"/api/v1/notifications/{delivered[0].id}", headers=headers
        )
        assert hidden.status_code == 404
        forbidden = await client.post(
            "/api/v1/notifications/test",
            headers=headers,
            json={"channel": "email", "subject": "Denied", "body": "Denied"},
        )
        assert forbidden.status_code == 403

    retry_event = PromotionApplied(
        promotion_id=uuid7(),
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=2,
    )
    await PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(db_session)).write(
        retry_event
    )
    retry_at = datetime.now(UTC)
    retry_dispatcher = _dispatcher(
        db_session, NullNotificationGateway(failures_before_success=1)
    )
    assert await retry_dispatcher.dispatch_pending(now=retry_at) == 3
    retrying = (
        await db_session.scalars(
            select(NotificationModel).where(
                NotificationModel.source_event_id == retry_event.event_id,
                NotificationModel.status == NotificationStatus.RETRYING,
            )
        )
    ).all()
    assert len(retrying) == 3
    assert all(
        value.next_retry_at == retry_at + timedelta(seconds=1) for value in retrying
    )
    assert (
        await db_session.scalar(
            select(func.count(NotificationFailureModel.id)).where(
                NotificationFailureModel.notification_id.in_(
                    [value.id for value in retrying]
                )
            )
        )
        == 3
    )
    assert (
        await retry_dispatcher.dispatch_pending(now=retry_at + timedelta(seconds=1))
        == 3
    )
    statuses = set(
        await db_session.scalars(
            select(NotificationModel.status).where(
                NotificationModel.source_event_id == retry_event.event_id,
                NotificationModel.deleted_at.is_(None),
            )
        )
    )
    assert statuses == {NotificationStatus.DELIVERED}
    preference_model = await db_session.scalar(
        select(NotificationPreferenceModel).where(
            NotificationPreferenceModel.customer_id == authenticated_identity.user.id
        )
    )
    assert preference_model is not None and preference_model.marketing_opt_in is False
    template_count = await db_session.scalar(
        select(func.count(NotificationTemplateModel.id))
    )
    assert template_count is not None and template_count >= 52

    failed_event = PromotionApplied(
        promotion_id=uuid7(),
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=3,
    )
    await PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(db_session)).write(
        failed_event
    )
    failed_before = _metric("fashion_network_notifications_failed_total", "email")
    failing = _dispatcher(
        db_session, NullNotificationGateway(failures_before_success=99)
    )
    assert await failing.dispatch_pending(now=retry_at) == 3
    assert await failing.dispatch_pending(now=retry_at + timedelta(seconds=1)) == 3
    assert await failing.dispatch_pending(now=retry_at + timedelta(seconds=3)) == 3
    failed_statuses = set(
        await db_session.scalars(
            select(NotificationModel.status).where(
                NotificationModel.source_event_id == failed_event.event_id,
                NotificationModel.deleted_at.is_(None),
            )
        )
    )
    assert failed_statuses == {NotificationStatus.FAILED}
    failed_source = await db_session.get(EventOutboxModel, failed_event.event_id)
    assert failed_source is not None and failed_source.status.value == "published"
    assert (
        _metric("fashion_network_notifications_failed_total", "email")
        == failed_before + 1
    )
