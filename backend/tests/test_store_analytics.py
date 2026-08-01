from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from prometheus_client import generate_latest
from pydantic import JsonValue
from pytest import MonkeyPatch
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from uuid6 import uuid7

from app.common.api import install_custom_openapi
from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.core.config import Settings, get_settings
from app.modules.identity.application.schemas import UserCreate
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyUserRepository,
)
from app.modules.stores.api.analytics_router import router as analytics_router
from app.modules.stores.application.analytics_services import (
    StoreAnalyticsAuditService,
    StoreAnalyticsService,
)
from app.modules.stores.domain import (
    AnalyticsPeriod,
    DailyMetricsCreated,
    MetricType,
    StoreAddress,
    StoreContact,
    StoreMediaType,
    StoreMetricRecorded,
)
from app.modules.stores.infrastructure.analytics_events import (
    StoreAnalyticsEventPublisher,
)
from app.modules.stores.infrastructure.persistence.analytics_models import (
    StoreDailyMetricsModel,
)
from app.modules.stores.infrastructure.persistence.analytics_repositories import (
    SqlAlchemyStoreAnalyticsRepository,
    SqlAlchemyStoreAnalyticsSourceRepository,
)
from app.modules.stores.infrastructure.persistence.media_repositories import (
    SqlAlchemyStoreMediaRepository,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"
NOW = datetime(2026, 8, 4, 10, tzinfo=UTC)


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class SourceEvent:
    name: str
    store_id: UUID
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = NOW
    correlation_id: UUID | None = None
    schema_version: ClassVar[int] = 1

    @property
    def event_name(self) -> str:
        return self.name

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"store_id": str(self.store_id)}


@pytest.fixture
def migrated_analytics_database(
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
async def analytics_session(
    migrated_analytics_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_analytics_database
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


async def _owner(session: AsyncSession, email: str = "analytics@example.com") -> UUID:
    user = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email, display_name="Analytics Owner", password_hash=ARGON2_HASH
        )
    )
    return user.id


async def _store(session: AsyncSession, owner_id: UUID) -> UUID:
    store = await SqlAlchemyStoreRepository(session).add(
        owner_id=owner_id,
        name="Analytics Store",
        slug=f"analytics-store-{owner_id.hex[:8]}",
        description=None,
        contact=StoreContact(phone="+91 9876543210", email="store@example.com"),
        address=StoreAddress(
            address="One Road",
            city="Imphal",
            district="Imphal West",
            state="Manipur",
            country="India",
            postal_code="795001",
            latitude=Decimal("24.817"),
            longitude=Decimal("93.9368"),
        ),
        logo_url=None,
        banner_url=None,
    )
    return store.id


def _service(
    session: AsyncSession, events: RecordingPublisher
) -> StoreAnalyticsService:
    return StoreAnalyticsService(
        SqlAlchemyStoreRepository(session),
        SqlAlchemyStoreAnalyticsRepository(session),
        SqlAlchemyStoreAnalyticsSourceRepository(session),
        StoreAnalyticsAuditService(events),
    )


async def test_record_event_creates_daily_metric_and_safe_events(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    events = RecordingPublisher()
    service = _service(analytics_session, events)

    recorded = await service.record_event(
        store_id=store,
        metric_type=MetricType.PROFILE_VIEW,
        occurred_at=NOW,
    )
    rows, total = await service.daily(
        store, owner, AnalyticsPeriod(NOW.date(), NOW.date()), offset=0, limit=25
    )

    assert recorded is not None
    assert total == 1
    assert rows[0].profile_views == 1
    assert [event.event_name for event in events.events] == [
        StoreMetricRecorded.event_name,
        DailyMetricsCreated.event_name,
    ]
    assert set(events.events[0].payload) == {
        "store_id",
        "metric_type",
        "metric_date",
        "value",
    }


async def test_duplicate_source_event_is_not_counted_twice(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    service = _service(analytics_session, RecordingPublisher())
    event_id = uuid7()

    first = await service.record_event(
        store_id=store,
        metric_type=MetricType.GALLERY_VIEW,
        occurred_at=NOW,
        event_id=event_id,
    )
    duplicate = await service.record_event(
        store_id=store,
        metric_type=MetricType.GALLERY_VIEW,
        occurred_at=NOW,
        event_id=event_id,
    )
    summary = await service.summary(
        store, owner, AnalyticsPeriod(NOW.date(), NOW.date())
    )

    assert first is not None
    assert duplicate is None
    assert summary.gallery_views == 1


async def test_aggregation_date_filtering_pagination_and_versions(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    service = _service(analytics_session, RecordingPublisher())
    for offset in range(3):
        await service.record_event(
            store_id=store,
            metric_type=MetricType.PROFILE_VIEW,
            occurred_at=NOW + timedelta(days=offset),
        )
    await service.record_event(
        store_id=store,
        metric_type=MetricType.PROFILE_VIEW,
        occurred_at=NOW,
    )

    result = await service.analytics(
        store,
        owner,
        AnalyticsPeriod(NOW.date(), (NOW + timedelta(days=2)).date()),
        offset=0,
        limit=2,
    )

    assert result.total_days == 3
    assert len(result.daily) == 2
    assert result.summary.profile_views == 4
    first_day = next(row for row in result.daily if row.metric_date != NOW.date())
    assert first_day.version == 1
    repository = SqlAlchemyStoreAnalyticsRepository(analytics_session)
    rows, _ = await repository.list_daily(
        store, date_from=NOW.date(), date_to=NOW.date(), offset=0, limit=1
    )
    assert rows[0].version == 2


async def test_storage_accounting_subtracts_deleted_media(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    media_repository = SqlAlchemyStoreMediaRepository(analytics_session)
    media = await media_repository.add(
        store_id=store,
        uploaded_by_id=owner,
        media_type=StoreMediaType.GALLERY,
        original_filename="image.png",
        stored_filename="stored.png",
        extension=".png",
        mime_type="image/png",
        file_size=128,
        width=10,
        height=10,
        orientation=1,
        aspect_ratio=Decimal("1"),
        checksum_sha256="a" * 64,
        bucket="media",
        object_key=f"stores/{store}/gallery/stored.png",
        etag="etag",
        display_order=0,
        is_public=True,
    )
    service = _service(analytics_session, RecordingPublisher())
    await service.record_event(
        store_id=store,
        metric_type=MetricType.MEDIA_UPLOAD,
        occurred_at=NOW,
    )
    assert await service.storage(store, owner) == 128

    deleted = await media_repository.soft_delete(
        store, media.id, deleted_at=NOW, expected_version=media.version
    )
    assert deleted is not None
    await service.record_event(
        store_id=store,
        metric_type=MetricType.MEDIA_DELETED,
        occurred_at=NOW,
    )
    assert await service.storage(store, owner) == 0
    summary = await service.summary(
        store, owner, AnalyticsPeriod(NOW.date(), NOW.date())
    )
    assert summary.media_uploads == 1
    assert summary.storage_bytes == 0


@pytest.mark.parametrize(
    ("event_name", "metric_type"),
    [
        ("store.verification.submitted", MetricType.VERIFICATION_SUBMISSION),
        ("store.verified", MetricType.VERIFICATION_APPROVAL),
        ("store.verification.rejected", MetricType.VERIFICATION_REJECTION),
        ("store.member.invited", MetricType.STAFF_INVITATION),
        ("store.member.accepted", MetricType.STAFF_ACCEPTANCE),
        ("store.logo.uploaded", MetricType.MEDIA_UPLOAD),
        ("store.banner.uploaded", MetricType.MEDIA_UPLOAD),
        ("store.gallery.uploaded", MetricType.MEDIA_UPLOAD),
        ("store.media.deleted", MetricType.MEDIA_DELETED),
    ],
)
async def test_existing_store_events_are_projected(
    analytics_session: AsyncSession,
    event_name: str,
    metric_type: MetricType,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    delegate = RecordingPublisher()
    publisher = StoreAnalyticsEventPublisher(
        delegate, _service(analytics_session, RecordingPublisher())
    )

    await publisher.publish(SourceEvent(event_name, store))

    rows, total = await SqlAlchemyStoreAnalyticsRepository(
        analytics_session
    ).list_daily(store, date_from=NOW.date(), date_to=NOW.date(), offset=0, limit=1)
    assert total == 1
    assert delegate.events[0].event_name == event_name
    assert rows[0].store_id == store
    if metric_type in {MetricType.MEDIA_UPLOAD, MetricType.MEDIA_DELETED}:
        assert rows[0].storage_bytes == 0


async def test_owner_isolation_and_explicit_admin_access(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    other = await _owner(analytics_session, "other-analytics@example.com")
    store = await _store(analytics_session, owner)
    service = _service(analytics_session, RecordingPublisher())
    period = AnalyticsPeriod(NOW.date(), NOW.date())

    with pytest.raises(AppError) as concealed:
        await service.summary(store, other, period)
    assert concealed.value.status_code == 404

    summary = await service.summary(store, other, period, admin_access=True)
    assert summary.store_id == store


@pytest.mark.parametrize(
    "metadata",
    [
        {"email": "private@example.com"},
        {"ip_address": "127.0.0.1"},
        {"access_token": "secret"},
        {"user_agent": "browser"},
    ],
)
async def test_sensitive_metadata_is_rejected(
    analytics_session: AsyncSession,
    metadata: dict[str, JsonValue],
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    with pytest.raises(AppError) as invalid:
        await _service(analytics_session, RecordingPublisher()).record_event(
            store_id=store,
            metric_type=MetricType.PROFILE_VIEW,
            occurred_at=NOW,
            metadata=metadata,
        )
    assert invalid.value.status_code == 422


async def test_invalid_period_and_naive_timestamp_are_rejected(
    analytics_session: AsyncSession,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    service = _service(analytics_session, RecordingPublisher())
    with pytest.raises(AppError):
        await service.summary(
            store, owner, AnalyticsPeriod(NOW.date(), NOW.date() - timedelta(days=1))
        )
    with pytest.raises(AppError):
        await service.record_event(
            store_id=store,
            metric_type=MetricType.PROFILE_VIEW,
            occurred_at=datetime(2026, 8, 4),
        )


async def test_constraints_indexes_metrics_and_repository_transaction(
    analytics_session: AsyncSession,
    database_url: str,
) -> None:
    owner = await _owner(analytics_session)
    store = await _store(analytics_session, owner)
    analytics_session.add(
        StoreDailyMetricsModel(
            store_id=store,
            metric_date=NOW.date(),
            profile_views=-1,
        )
    )
    with pytest.raises(IntegrityError):
        await analytics_session.flush()
    await analytics_session.rollback()

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            daily_indexes = await connection.run_sync(
                lambda connection_: inspect(connection_).get_indexes(
                    "store_daily_metrics"
                )
            )
            event_indexes = await connection.run_sync(
                lambda connection_: inspect(connection_).get_indexes(
                    "store_metric_events"
                )
            )
    finally:
        await engine.dispose()
    assert "ix_store_daily_metrics_store_date" in {
        index["name"] for index in daily_indexes
    }
    assert "ix_store_metric_events_event_type" in {
        index["name"] for index in event_indexes
    }
    exposition = generate_latest().decode()
    assert "fashion_network_store_metric_events_total" in exposition
    assert "fashion_network_store_daily_updates_total" in exposition
    assert "fashion_network_store_storage_bytes" in exposition
    assert "fashion_network_store_profile_views_total" in exposition


def test_openapi_documents_analytics_filters_and_authorization(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(analytics_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)
    schema = application.openapi()
    for suffix in ("", "/summary", "/daily", "/storage"):
        operation = schema["paths"][f"/api/v1/stores/{{store_id}}/analytics{suffix}"][
            "get"
        ]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {
                "kind": "any_permission",
                "values": ["store:view", "admin:access"],
            }
        ]
        assert operation["description"]
    daily_parameters = schema["paths"]["/api/v1/stores/{store_id}/analytics/daily"][
        "get"
    ]["parameters"]
    assert {parameter["name"] for parameter in daily_parameters} >= {
        "date_from",
        "date_to",
        "offset",
        "limit",
    }


def test_analytics_migration_downgrades_and_reupgrades(
    migrated_analytics_database: None,
    database_url: str,
    monkeypatch: MonkeyPatch,
) -> None:
    del migrated_analytics_database
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(BACKEND_ROOT / "alembic.ini")
    try:
        command.downgrade(config, "077498dfaa91")
        command.upgrade(config, "0f01b7088f73")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        get_settings.cache_clear()
