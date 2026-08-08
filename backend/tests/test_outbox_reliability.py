from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events import SqlAlchemyReliableOutboxRepository, TransactionalOutboxPublisher
from app.events.infrastructure.models import EventConsumerReceiptModel
from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.inventory.application.schemas import InventoryCreate
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryStatus, TrackingPolicy
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from app.modules.notifications.application.dispatchers import NotificationDispatcher
from app.modules.notifications.gateways import NullNotificationGateway
from app.modules.notifications.infrastructure.models import NotificationModel
from app.modules.notifications.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyNotificationOutboxRepository,
    SqlAlchemyNotificationRepository,
    SqlAlchemyPreferenceRepository,
    SqlAlchemyTemplateRepository,
)
from app.modules.products.domain import OutboxStatus, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.promotions.application.services import PromotionOutboxService
from app.modules.promotions.domain import PromotionApplied
from app.modules.promotions.infrastructure.repositories import (
    SqlAlchemyPromotionOutboxRepository,
)
from app.modules.stores.domain import Store
from tests.test_order import _authorized_client

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


async def test_inventory_and_outbox_rollback_atomically(
    authenticated_identity: AuthenticatedIdentity,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    savepoint = await db_session.begin_nested()
    service = InventoryService(
        SqlAlchemyInventoryRepository(db_session),
        TransactionalOutboxPublisher(db_session),
    )
    inventory = await service.create(
        InventoryCreate(
            variant_id=product_variant.id,
            quantity_on_hand=4,
            quantity_reserved=0,
            status=InventoryStatus.ACTIVE,
            tracking_policy=TrackingPolicy.TRACK,
            low_stock_threshold=1,
            actor_id=authenticated_identity.user.id,
        )
    )
    event_id = await db_session.scalar(
        select(EventOutboxModel.id).where(
            EventOutboxModel.aggregate_id == inventory.id,
            EventOutboxModel.event_name == "inventory.created",
        )
    )
    assert event_id is not None

    await savepoint.rollback()

    assert await db_session.get(InventoryItemModel, inventory.id) is None
    assert await db_session.get(EventOutboxModel, event_id) is None


async def test_concurrent_claim_crash_recovery_retry_exhaustion_and_broker_durability(
    session_factory: async_sessionmaker[AsyncSession],
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
) -> None:
    event = PromotionApplied(
        promotion_id=verified_store.id,
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=1,
    )
    try:
        async with session_factory() as producer:
            await PromotionOutboxService(
                SqlAlchemyPromotionOutboxRepository(producer)
            ).write(event)
            await producer.commit()

        now = datetime.now(UTC)

        async with session_factory() as durable_reader:
            durable = await durable_reader.get(EventOutboxModel, event.event_id)
            assert durable is not None
            assert durable.status is OutboxStatus.PENDING

        async with session_factory() as first, session_factory() as competitor:
            first_repository = SqlAlchemyReliableOutboxRepository(first)
            competing_repository = SqlAlchemyReliableOutboxRepository(competitor)
            first_claim = await first_repository.claim(
                [event.event_name],
                worker_id="worker-a",
                now=now,
                lease_timeout=timedelta(seconds=30),
                limit=1,
            )
            competing_claim = await competing_repository.claim(
                [event.event_name],
                worker_id="worker-b",
                now=now,
                lease_timeout=timedelta(seconds=30),
                limit=1,
            )
            assert len(first_claim) == 1
            assert competing_claim == []
            await first.commit()
            await competitor.rollback()

        recovered_at = now + timedelta(seconds=31)
        async with session_factory() as recovery:
            repository = SqlAlchemyReliableOutboxRepository(recovery)
            recovered = await repository.claim(
                [event.event_name],
                worker_id="worker-c",
                now=recovered_at,
                lease_timeout=timedelta(seconds=30),
                limit=1,
            )
            assert len(recovered) == 1 and recovered[0].recovered
            assert recovered[0].attempts == 2
            assert await repository.mark_failed(
                event.event_id,
                worker_id="worker-c",
                now=recovered_at,
                error="temporary database failure",
                max_attempts=3,
                retry_base_seconds=5,
            )
            await recovery.commit()

        retry_at = recovered_at + timedelta(seconds=10)
        async with session_factory() as retry:
            repository = SqlAlchemyReliableOutboxRepository(retry)
            assert (
                await repository.claim(
                    [event.event_name],
                    worker_id="worker-d",
                    now=retry_at - timedelta(microseconds=1),
                    lease_timeout=timedelta(seconds=30),
                    limit=1,
                )
                == []
            )
            terminal = await repository.claim(
                [event.event_name],
                worker_id="worker-d",
                now=retry_at,
                lease_timeout=timedelta(seconds=30),
                limit=1,
            )
            assert len(terminal) == 1 and terminal[0].attempts == 3
            assert await repository.mark_failed(
                event.event_id,
                worker_id="worker-d",
                now=retry_at,
                error="retry exhaustion",
                max_attempts=3,
                retry_base_seconds=5,
            )
            problems = await repository.inspect_problematic(
                now=retry_at,
                lease_timeout=timedelta(seconds=30),
                limit=10,
            )
            assert len(problems) == 1
            assert problems[0].status is OutboxStatus.FAILED
            assert problems[0].last_error == "retry exhaustion"
            await retry.commit()
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(
                delete(EventConsumerReceiptModel).where(
                    EventConsumerReceiptModel.event_id == event.event_id
                )
            )
            await cleanup.execute(
                delete(EventOutboxModel).where(EventOutboxModel.id == event.event_id)
            )
            await cleanup.commit()


async def test_notification_consumption_is_idempotent_and_receipted(
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    db_session: AsyncSession,
) -> None:
    event = PromotionApplied(
        promotion_id=verified_store.id,
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=2,
    )
    await PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(db_session)).write(
        event
    )
    dispatcher = NotificationDispatcher(
        SqlAlchemyNotificationRepository(db_session),
        SqlAlchemyPreferenceRepository(db_session),
        SqlAlchemyTemplateRepository(db_session),
        SqlAlchemyDeliveryRepository(db_session),
        SqlAlchemyNotificationOutboxRepository(db_session),
        NullNotificationGateway(),
    )

    assert await dispatcher.dispatch_pending() == 2
    assert await dispatcher.dispatch_pending() == 0
    assert (
        await db_session.scalar(
            select(func.count(NotificationModel.id)).where(
                NotificationModel.source_event_id == event.event_id
            )
        )
        == 4
    )
    assert (
        await db_session.scalar(
            select(func.count(EventConsumerReceiptModel.id)).where(
                EventConsumerReceiptModel.event_id == event.event_id,
                EventConsumerReceiptModel.consumer_name == "notifications",
            )
        )
        == 1
    )


async def test_admin_can_inspect_and_recover_terminal_event(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    db_session: AsyncSession,
) -> None:
    event = PromotionApplied(
        promotion_id=verified_store.id,
        customer_id=authenticated_identity.user.id,
        store_id=verified_store.id,
        version=3,
    )
    await PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(db_session)).write(
        event
    )
    now = datetime.now(UTC)
    repository = SqlAlchemyReliableOutboxRepository(db_session)
    assert await repository.claim(
        [event.event_name],
        worker_id="failed-worker",
        now=now,
        lease_timeout=timedelta(seconds=30),
        limit=1,
    )
    assert await repository.mark_failed(
        event.event_id,
        worker_id="failed-worker",
        now=now,
        error="provider unavailable",
        max_attempts=1,
        retry_base_seconds=1,
    )

    async with _authorized_client(
        async_client,
        authenticated_identity,
        db_session,
        role="admin",
    ) as (client, headers):
        inspection = await client.get("/api/v1/admin/events", headers=headers)
        recovery = await client.post(
            f"/api/v1/admin/events/{event.event_id}/recover", headers=headers
        )

    assert inspection.status_code == 200, inspection.text
    assert str(event.event_id) in {item["id"] for item in inspection.json()["items"]}
    assert recovery.status_code == 200, recovery.text
    assert recovery.json()["status"] == "pending"
    persisted = await db_session.get(EventOutboxModel, event.event_id)
    assert persisted is not None
    await db_session.refresh(persisted)
    assert persisted.status is OutboxStatus.PENDING
    assert persisted.locked_at is None and persisted.locked_by is None
