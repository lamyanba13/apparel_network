from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
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
from sqlalchemy import inspect
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
from app.modules.stores.api.dependencies import store_service_dependency
from app.modules.stores.api.router import router as stores_router
from app.modules.stores.application.schemas import StoreCreate, StoreUpdate
from app.modules.stores.application.services import (
    StoreLifecycleService,
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.domain import (
    Store,
    StoreAddress,
    StoreClosed,
    StoreContact,
    StoreCreated,
    StoreStatus,
    StoreSubmitted,
    StoreSuspended,
    StoreUpdated,
    StoreVerified,
    VerificationStatus,
)
from app.modules.stores.infrastructure.persistence.models import StoreModel
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@pytest.fixture
def migrated_store_database(
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
async def store_session(
    migrated_store_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_store_database
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


async def _owner(session: AsyncSession, email: str = "owner@example.com") -> UUID:
    user = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email,
            display_name="Store Owner",
            password_hash=ARGON2_HASH,
        )
    )
    return user.id


def _values(owner_id: UUID, *, name: str = "Imphal Threads") -> StoreCreate:
    return StoreCreate(
        owner_id=owner_id,
        name=name,
        description="Independent clothing store.",
        contact=StoreContact(
            phone="+91 98765 43210",
            email="SHOP@Example.COM",
            website="https://example.com",
        ),
        address=StoreAddress(
            address="10 Kangla Road",
            city="Imphal",
            district="Imphal West",
            state="Manipur",
            country="India",
            postal_code="795001",
            latitude=Decimal("24.817000"),
            longitude=Decimal("93.936800"),
        ),
    )


def _service(
    session: AsyncSession,
    events: RecordingPublisher,
) -> StoreService:
    return StoreService(
        SqlAlchemyStoreRepository(session),
        events,
        StoreValidationService(),
        StoreSlugService(),
    )


async def test_store_crud_is_owner_scoped_versioned_and_soft_deleted(
    store_session: AsyncSession,
) -> None:
    owner_id = await _owner(store_session)
    other_owner_id = await _owner(store_session, "other@example.com")
    events = RecordingPublisher()
    service = _service(store_session, events)

    created = await service.create(_values(owner_id))

    assert created.id.version == 7
    assert created.slug == "imphal-threads"
    assert created.contact.email == "shop@example.com"
    assert created.status is StoreStatus.DRAFT
    assert created.verification_status is VerificationStatus.UNVERIFIED
    assert store_session.in_transaction()
    assert events.events[-1].event_name == StoreCreated.event_name

    items, total = await service.list_owned(owner_id, offset=0, limit=25)
    assert total == 1
    assert [item.id for item in items] == [created.id]

    with pytest.raises(AppError) as concealed:
        await service.get_owned(created.id, other_owner_id)
    assert concealed.value.status_code == 404

    updated = await service.update_owned(
        created.id,
        owner_id,
        StoreUpdate(
            values={"name": "  Imphal   Threads Collective  "},
            expected_version=created.version,
        ),
    )
    assert updated.name == "Imphal Threads Collective"
    assert updated.slug == created.slug
    assert updated.version == created.version + 1
    assert events.events[-1].event_name == StoreUpdated.event_name

    with pytest.raises(AppError) as stale:
        await service.update_owned(
            created.id,
            owner_id,
            StoreUpdate(values={"name": "Stale Update"}, expected_version=1),
        )
    assert stale.value.status_code == 409

    await service.delete_owned(created.id, owner_id)
    assert events.events[-1].event_name == StoreClosed.event_name
    assert (
        await SqlAlchemyStoreRepository(store_session).get_for_owner(
            created.id, owner_id
        )
        is None
    )
    persisted = await store_session.get(StoreModel, created.id)
    assert persisted is not None
    assert persisted.status is StoreStatus.CLOSED
    assert persisted.deleted_at is not None


async def test_store_slug_collision_is_resolved(
    store_session: AsyncSession,
) -> None:
    owner_id = await _owner(store_session)
    events = RecordingPublisher()
    service = _service(store_session, events)

    first = await service.create(_values(owner_id))
    second = await service.create(_values(owner_id))

    assert first.slug == "imphal-threads"
    assert second.slug.startswith("imphal-threads-")
    assert first.slug != second.slug


async def test_store_constraints_and_indexes_are_explicit(
    store_session: AsyncSession,
) -> None:
    owner_id = await _owner(store_session)
    repository = SqlAlchemyStoreRepository(store_session)
    created = await repository.add(
        owner_id=owner_id,
        name="Valid Store",
        slug="valid-store",
        description=None,
        contact=StoreContact(phone="+91 9876543210", email="valid@example.com"),
        address=_values(owner_id).address,
        logo_url=None,
        banner_url=None,
    )
    store_session.add(
        StoreModel(
            owner_id=owner_id,
            name="Other Store",
            slug=created.slug,
            phone="+91 9876543211",
            email="other-store@example.com",
            address="One Road",
            city="Imphal",
            district="Imphal West",
            state="Manipur",
            country="India",
            postal_code="795001",
        )
    )
    with pytest.raises(IntegrityError):
        await store_session.flush()


async def test_store_table_metadata_contains_required_indexes(
    migrated_store_database: None,
    database_url: str,
) -> None:
    del migrated_store_database
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes("stores")
            )
    finally:
        await engine.dispose()

    assert {index["name"] for index in indexes} >= {
        "ix_stores_active_public",
        "ix_stores_owner_id_status",
        "ix_stores_status_verification",
    }


def test_store_validation_rejects_invalid_contact_and_coordinates() -> None:
    validation = StoreValidationService()
    owner_id = UUID(int=1)

    with pytest.raises(AppError) as invalid_email:
        validation.validate_create(
            StoreCreate(
                owner_id=owner_id,
                name="Invalid Contact",
                description=None,
                contact=StoreContact(
                    phone="+91 9876543210",
                    email="invalid-email",
                ),
                address=_values(owner_id).address,
            )
        )
    assert invalid_email.value.status_code == 422

    with pytest.raises(AppError) as incomplete_coordinates:
        validation.validate_changes({"latitude": Decimal("24.8")})
    assert incomplete_coordinates.value.status_code == 422


async def test_store_lifecycle_emits_events_and_updates_metrics(
    store_session: AsyncSession,
) -> None:
    owner_id = await _owner(store_session)
    events = RecordingPublisher()
    created = await _service(store_session, events).create(_values(owner_id))
    lifecycle = StoreLifecycleService(
        SqlAlchemyStoreRepository(store_session),
        events,
    )

    submitted = await lifecycle.submit(created.id)
    assert submitted.status is StoreStatus.PENDING_REVIEW
    assert submitted.verification_status is VerificationStatus.PENDING
    assert events.events[-1].event_name == StoreSubmitted.event_name

    verified = await lifecycle.verify(created.id)
    assert verified.status is StoreStatus.ACTIVE
    assert verified.verification_status is VerificationStatus.VERIFIED
    assert events.events[-1].event_name == StoreVerified.event_name

    exposition = generate_latest().decode()
    assert "fashion_network_stores_created_total" in exposition
    assert "fashion_network_stores_active_total 1.0" in exposition
    assert "fashion_network_stores_verified_total 1.0" in exposition

    with pytest.raises(AppError) as invalid_transition:
        await lifecycle.verify(created.id)
    assert invalid_transition.value.status_code == 409

    second = await _service(store_session, events).create(
        _values(owner_id, name="Second Store")
    )
    await lifecycle.submit(second.id)
    suspended = await lifecycle.suspend(second.id)
    assert suspended.status is StoreStatus.SUSPENDED
    assert events.events[-1].event_name == StoreSuspended.event_name


def test_store_openapi_documents_crud_security_and_permissions(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(stores_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)

    schema = application.openapi()
    expected = {
        ("post", "/api/v1/stores", "store:create"),
        ("get", "/api/v1/stores", "store:view"),
        ("get", "/api/v1/stores/{store_id}", "store:view"),
        ("patch", "/api/v1/stores/{store_id}", "store:update"),
        ("delete", "/api/v1/stores/{store_id}", "store:delete"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
    assert "/api/v1/stores/{store_id}/verify" not in schema["paths"]


def test_store_api_uses_permission_service_without_role_comparisons() -> None:
    store_id = UUID(int=30)
    owner_id = UUID(int=31)
    calls: list[str] = []
    now_store = Store(
        id=store_id,
        owner_id=owner_id,
        name="API Store",
        slug="api-store",
        description=None,
        contact=StoreContact(phone="+91 9876543210", email="api@example.com"),
        address=StoreAddress(
            address="One Road",
            city="Imphal",
            district="Imphal West",
            state="Manipur",
            country="India",
            postal_code="795001",
        ),
        logo_url=None,
        banner_url=None,
        status=StoreStatus.DRAFT,
        verification_status=VerificationStatus.UNVERIFIED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=None,
        version=1,
    )

    class StubAuthorizationService:
        async def require_permission(
            self,
            identity: object,
            permission: str,
        ) -> None:
            del identity
            calls.append(permission)

    class StubStoreService:
        async def get_owned(self, requested_id: UUID, requested_owner: UUID) -> Store:
            assert requested_id == store_id
            assert requested_owner == owner_id
            return now_store

    identity = SimpleNamespace(
        user=SimpleNamespace(id=owner_id),
        session=SimpleNamespace(id=UUID(int=32)),
    )
    application = FastAPI()
    application.include_router(stores_router, prefix="/api/v1")
    application.dependency_overrides[current_identity_dependency] = lambda: identity
    application.dependency_overrides[authorization_service_dependency] = (
        StubAuthorizationService
    )
    application.dependency_overrides[store_service_dependency] = StubStoreService

    with TestClient(application) as client:
        response = client.get(f"/api/v1/stores/{store_id}")

    assert response.status_code == 200
    assert response.json()["owner_id"] == str(owner_id)
    assert calls == ["store:view"]
