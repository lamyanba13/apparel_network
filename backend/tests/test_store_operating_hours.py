from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from pytest import MonkeyPatch
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.api import install_custom_openapi
from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.core.config import Settings, get_settings
from app.modules.identity.api.authorization import authorization_service_dependency
from app.modules.identity.api.dependencies import current_identity_dependency
from app.modules.identity.application.schemas import UserCreate
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyUserRepository,
)
from app.modules.stores.api.dependencies import (
    store_operating_hours_service_dependency,
)
from app.modules.stores.api.operating_hours_router import (
    router as store_operating_hours_router,
)
from app.modules.stores.application.operating_hours_schemas import (
    StoreHoursCreate,
    StoreHoursUpdate,
)
from app.modules.stores.application.operating_hours_services import (
    StoreOperatingHoursAuditService,
    StoreOperatingHoursService,
    StoreOperatingHoursValidationService,
)
from app.modules.stores.domain import (
    OpenState,
    StoreAddress,
    StoreContact,
    StoreHoursCreated,
    StoreHoursDeleted,
    StoreHoursUpdated,
    StoreOpened,
    StoreScheduleActivated,
    StoreScheduleExpired,
)
from app.modules.stores.domain.operating_hours_events import (
    StoreClosed as StoreHoursClosed,
)
from app.modules.stores.infrastructure.persistence.models import StoreModel
from app.modules.stores.infrastructure.persistence.operating_hours_models import (
    StoreOperatingHoursModel,
)
from app.modules.stores.infrastructure.persistence.operating_hours_repositories import (
    SqlAlchemyStoreOperatingHoursRepository,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"
MONDAY_MORNING = datetime(2026, 8, 3, 4, 30, tzinfo=UTC)  # 10:00 Asia/Kolkata


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@pytest.fixture
def migrated_hours_database(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> Iterator[None]:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def hours_session(
    migrated_hours_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_hours_database
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


async def _owner(session: AsyncSession, email: str = "hours-owner@example.com") -> UUID:
    user = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email,
            display_name="Hours Owner",
            password_hash=ARGON2_HASH,
        )
    )
    return user.id


async def _store(session: AsyncSession, owner_id: UUID) -> UUID:
    store = await SqlAlchemyStoreRepository(session).add(
        owner_id=owner_id,
        name="Schedule Store",
        slug=f"schedule-store-{owner_id.hex[:8]}",
        description=None,
        contact=StoreContact(
            phone="+91 9876543210",
            email="schedule@example.com",
        ),
        address=StoreAddress(
            address="One Road",
            city="Imphal",
            district="Imphal West",
            state="Manipur",
            country="India",
            postal_code="795001",
            latitude=Decimal("24.817000"),
            longitude=Decimal("93.936800"),
        ),
        logo_url=None,
        banner_url=None,
    )
    return store.id


def _values(
    *,
    opening: time | None = time(9),
    closing: time | None = time(17),
    closed: bool = False,
    all_day: bool = False,
    priority: int = 0,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    timezone: str = "Asia/Kolkata",
) -> StoreHoursCreate:
    return StoreHoursCreate(
        day_of_week=0,
        timezone=timezone,
        opening_time=opening,
        closing_time=closing,
        is_closed=closed,
        is_24_hours=all_day,
        effective_from=effective_from,
        effective_until=effective_until,
        priority=priority,
        notes="Monday schedule",
    )


def _service(
    session: AsyncSession,
    events: RecordingPublisher,
) -> StoreOperatingHoursService:
    return StoreOperatingHoursService(
        SqlAlchemyStoreRepository(session),
        SqlAlchemyStoreOperatingHoursRepository(session),
        StoreOperatingHoursValidationService(),
        StoreOperatingHoursAuditService(events),
    )


async def test_schedule_creation_listing_uuid_and_repository_transaction(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    events = RecordingPublisher()

    created = await _service(hours_session, events).create(
        store_id,
        owner_id,
        _values(),
    )
    items = await _service(hours_session, events).list(store_id, owner_id)

    assert created.id.version == 7
    assert created.store_id == store_id
    assert created.version == 1
    assert [item.id for item in items] == [created.id]
    assert hours_session.in_transaction()
    assert events.events[0].event_name == StoreHoursCreated.event_name


async def test_multiple_non_overlapping_intervals_are_supported(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())

    await service.create(store_id, owner_id, _values(opening=time(9), closing=time(12)))
    await service.create(
        store_id,
        owner_id,
        _values(opening=time(13), closing=time(17)),
    )
    today = await service.today(store_id, owner_id, now=MONDAY_MORNING)

    assert today is not None
    assert len(today.intervals) == 2
    assert today.priority == 0


async def test_overlapping_interval_at_same_priority_is_rejected(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values(opening=time(9), closing=time(13)))

    with pytest.raises(AppError) as conflict:
        await service.create(
            store_id,
            owner_id,
            _values(opening=time(12), closing=time(17)),
        )

    assert conflict.value.status_code == 409


async def test_closed_day_resolves_closed_status(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(
        store_id,
        owner_id,
        _values(opening=None, closing=None, closed=True),
    )

    status = await service.status(store_id, owner_id, now=MONDAY_MORNING)

    assert status.current_status is OpenState.CLOSED
    assert not status.open_now
    assert status.current_interval is None


async def test_twenty_four_hour_schedule_resolves_open(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(
        store_id,
        owner_id,
        _values(opening=None, closing=None, all_day=True),
    )

    status = await service.status(store_id, owner_id, now=MONDAY_MORNING)

    assert status.open_now
    assert status.is_24_hours
    assert status.current_status is OpenState.OPEN


async def test_temporary_higher_priority_schedule_overrides_recurring(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values())
    await service.create(
        store_id,
        owner_id,
        _values(
            opening=None,
            closing=None,
            closed=True,
            priority=10,
            effective_from=MONDAY_MORNING - timedelta(hours=1),
            effective_until=MONDAY_MORNING + timedelta(hours=1),
        ),
    )

    status = await service.status(store_id, owner_id, now=MONDAY_MORNING)

    assert not status.open_now
    assert status.temporary_override
    assert status.today_schedule is not None
    assert status.today_schedule.priority == 10


async def test_expired_override_is_ignored(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values())
    await service.create(
        store_id,
        owner_id,
        _values(
            opening=None,
            closing=None,
            closed=True,
            priority=10,
            effective_from=MONDAY_MORNING - timedelta(days=2),
            effective_until=MONDAY_MORNING - timedelta(days=1),
        ),
    )

    status = await service.status(store_id, owner_id, now=MONDAY_MORNING)

    assert status.open_now
    assert not status.temporary_override


async def test_next_opening_and_closing_are_calculated_in_store_timezone(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values())
    before_open = datetime(2026, 8, 3, 2, 30, tzinfo=UTC)  # 08:00 local

    status = await service.status(store_id, owner_id, now=before_open)

    assert status.next_opening == datetime(2026, 8, 3, 3, 30, tzinfo=UTC)
    assert status.next_closing == datetime(2026, 8, 3, 11, 30, tzinfo=UTC)
    assert status.timezone == "Asia/Kolkata"


async def test_priority_resolution_selects_highest_active_priority(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values(priority=0))
    await service.create(
        store_id,
        owner_id,
        _values(opening=time(10), closing=time(16), priority=5),
    )

    today = await service.today(store_id, owner_id, now=MONDAY_MORNING)

    assert today is not None
    assert today.priority == 5
    assert today.intervals[0].opening_time == time(10)


async def test_update_uses_optimistic_locking(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    created = await service.create(store_id, owner_id, _values())

    updated = await service.update(
        store_id,
        created.id,
        owner_id,
        StoreHoursUpdate(
            expected_version=created.version,
            values={"closing_time": time(18)},
        ),
    )
    assert updated.closing_time == time(18)
    assert updated.version == 2

    with pytest.raises(AppError) as stale:
        await service.update(
            store_id,
            created.id,
            owner_id,
            StoreHoursUpdate(
                expected_version=created.version,
                values={"closing_time": time(19)},
            ),
        )
    assert stale.value.status_code == 409


async def test_delete_is_soft_and_cross_store_access_is_concealed(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    other_owner = await _owner(hours_session, "hours-other@example.com")
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    created = await service.create(store_id, owner_id, _values())

    with pytest.raises(AppError) as concealed:
        await service.delete(store_id, created.id, other_owner)
    assert concealed.value.status_code == 404

    await service.delete(store_id, created.id, owner_id)
    persisted = await hours_session.get(StoreOperatingHoursModel, created.id)
    assert persisted is not None
    assert persisted.deleted_at is not None
    assert (
        await SqlAlchemyStoreOperatingHoursRepository(hours_session).get(
            store_id, created.id
        )
        is None
    )


@pytest.mark.parametrize(
    "values",
    [
        _values(opening=time(17), closing=time(9)),
        _values(opening=None, closing=None),
        _values(opening=None, closing=None, closed=True, all_day=True),
        _values(timezone="Not/AZone"),
        _values(priority=-1),
        _values(
            effective_from=MONDAY_MORNING,
            effective_until=MONDAY_MORNING - timedelta(hours=1),
        ),
    ],
)
def test_validation_rejects_invalid_schedule(values: StoreHoursCreate) -> None:
    with pytest.raises(AppError) as invalid:
        StoreOperatingHoursValidationService().validate_create(values)
    assert invalid.value.status_code == 422


async def test_store_timezone_mismatch_is_rejected(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    service = _service(hours_session, RecordingPublisher())
    await service.create(store_id, owner_id, _values())

    with pytest.raises(AppError) as invalid:
        await service.create(
            store_id,
            owner_id,
            _values(
                opening=time(18),
                closing=time(20),
                timezone="UTC",
            ),
        )
    assert invalid.value.status_code == 422


async def test_database_constraints_and_indexes(
    hours_session: AsyncSession,
    database_url: str,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    hours_session.add(
        StoreOperatingHoursModel(
            store_id=store_id,
            day_of_week=7,
            timezone="Asia/Kolkata",
            opening_time=time(9),
            closing_time=time(17),
            priority=0,
        )
    )
    with pytest.raises(IntegrityError):
        await hours_session.flush()
    await hours_session.rollback()

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "store_operating_hours"
                )
            )
    finally:
        await engine.dispose()
    assert {index["name"] for index in indexes} >= {
        "ix_store_hours_active_store",
        "ix_store_hours_effective_range",
        "ix_store_hours_resolution",
    }


async def test_events_are_safe_and_metrics_are_low_cardinality(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    events = RecordingPublisher()
    service = _service(hours_session, events)
    created = await service.create(store_id, owner_id, _values())
    await service.status(store_id, owner_id, now=MONDAY_MORNING)
    updated = await service.update(
        store_id,
        created.id,
        owner_id,
        StoreHoursUpdate(expected_version=created.version, values={"notes": "Open"}),
    )
    await service.delete(store_id, updated.id, owner_id)

    names = {event.event_name for event in events.events}
    assert {
        StoreHoursCreated.event_name,
        StoreHoursUpdated.event_name,
        StoreHoursDeleted.event_name,
        StoreOpened.event_name,
        StoreScheduleActivated.event_name,
    } <= names
    for event in events.events:
        assert set(event.payload) == {"store_id", "schedule_id", "status"}

    exposition = generate_latest().decode()
    assert "fashion_network_store_hours_updates_total" in exposition
    assert "fashion_network_store_hours_queries_total" in exposition
    assert "fashion_network_store_open_total" in exposition
    assert "fashion_network_store_closed_total" in exposition


def test_all_operating_hours_event_contracts_have_safe_payloads() -> None:
    kwargs = {
        "store_id": UUID(int=1),
        "schedule_id": UUID(int=2),
        "status": OpenState.CLOSED,
    }
    for event_type in (
        StoreHoursCreated,
        StoreHoursUpdated,
        StoreHoursDeleted,
        StoreOpened,
        StoreHoursClosed,
        StoreScheduleActivated,
        StoreScheduleExpired,
    ):
        event = event_type(**kwargs)
        assert set(event.payload) == {"store_id", "schedule_id", "status"}


def test_openapi_documents_all_hours_routes_and_permissions(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(store_operating_hours_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)

    schema = application.openapi()
    expected = {
        ("post", "/api/v1/stores/{store_id}/hours", "store:update"),
        ("get", "/api/v1/stores/{store_id}/hours", "store:view"),
        ("get", "/api/v1/stores/{store_id}/hours/today", "store:view"),
        (
            "patch",
            "/api/v1/stores/{store_id}/hours/{schedule_id}",
            "store:update",
        ),
        (
            "delete",
            "/api/v1/stores/{store_id}/hours/{schedule_id}",
            "store:update",
        ),
        ("get", "/api/v1/stores/{store_id}/status", "store:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
        assert operation["description"]
        assert operation["responses"]


def test_status_api_uses_permission_service_without_role_comparisons() -> None:
    store_id = UUID(int=50)
    owner_id = UUID(int=51)
    calls: list[str] = []

    class StubAuthorizationService:
        async def require_permission(
            self,
            identity: object,
            permission: str,
        ) -> None:
            del identity
            calls.append(permission)

    class StubHoursService:
        async def status(self, requested_store: UUID, requested_owner: UUID) -> object:
            assert requested_store == store_id
            assert requested_owner == owner_id
            return SimpleNamespace(
                store_id=store_id,
                timezone="Asia/Kolkata",
                current_status=OpenState.CLOSED,
                open_now=False,
                is_24_hours=False,
                current_interval=None,
                today_schedule=None,
                next_opening=None,
                next_closing=None,
                temporary_override=False,
            )

    identity = SimpleNamespace(
        user=SimpleNamespace(id=owner_id),
        session=SimpleNamespace(id=UUID(int=52)),
    )
    application = FastAPI()
    application.include_router(store_operating_hours_router, prefix="/api/v1")
    application.dependency_overrides[current_identity_dependency] = lambda: identity
    application.dependency_overrides[authorization_service_dependency] = (
        StubAuthorizationService
    )
    application.dependency_overrides[store_operating_hours_service_dependency] = (
        StubHoursService
    )

    with TestClient(application) as client:
        response = client.get(f"/api/v1/stores/{store_id}/status")

    assert response.status_code == 200
    assert response.json()["current_status"] == "closed"
    assert calls == ["store:view"]


def test_operating_hours_migration_downgrades_and_reupgrades(
    migrated_hours_database: None,
    database_url: str,
    monkeypatch: MonkeyPatch,
) -> None:
    del migrated_hours_database
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(BACKEND_ROOT / "alembic.ini")
    try:
        command.downgrade(config, "2eb2bce458d5")
        command.upgrade(config, "077498dfaa91")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        get_settings.cache_clear()


async def test_repository_flushes_without_committing(
    hours_session: AsyncSession,
) -> None:
    owner_id = await _owner(hours_session)
    store_id = await _store(hours_session, owner_id)
    repository = SqlAlchemyStoreOperatingHoursRepository(hours_session)
    created = await repository.add(store_id, _values())

    assert hours_session.in_transaction()
    assert (
        await hours_session.scalar(
            select(StoreOperatingHoursModel.id).where(
                StoreOperatingHoursModel.id == created.id
            )
        )
        == created.id
    )
    assert (
        await hours_session.scalar(
            select(StoreModel.id).where(StoreModel.id == store_id)
        )
        == store_id
    )
