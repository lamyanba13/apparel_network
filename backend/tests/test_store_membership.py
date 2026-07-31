from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
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
from app.modules.stores.api.dependencies import store_membership_service_dependency
from app.modules.stores.api.membership_router import router as membership_router
from app.modules.stores.application.membership_schemas import (
    StoreMembershipInvitation,
    StoreMembershipUpdate,
)
from app.modules.stores.application.membership_services import (
    MembershipAuditService,
    MembershipLifecycleService,
    StoreInvitationService,
    StoreMembershipService,
)
from app.modules.stores.application.schemas import StoreCreate
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.domain import (
    StoreAddress,
    StoreContact,
    StoreMembership,
    StoreMembershipRole,
    StoreMembershipStatus,
)
from app.modules.stores.infrastructure.persistence.membership_repositories import (
    SqlAlchemyStoreMembershipRepository,
)
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
def migrated_membership_database(
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
async def membership_session(
    migrated_membership_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_membership_database
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


async def _user(session: AsyncSession, email: str) -> UUID:
    record = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email,
            display_name="Store Member",
            password_hash=ARGON2_HASH,
        )
    )
    return record.id


async def _store(
    session: AsyncSession,
    events: RecordingPublisher,
    owner_id: UUID,
) -> UUID:
    service = StoreService(
        SqlAlchemyStoreRepository(session),
        events,
        StoreValidationService(),
        StoreSlugService(),
    )
    store = await service.create(
        StoreCreate(
            owner_id=owner_id,
            name="Membership Store",
            description=None,
            contact=StoreContact(
                phone="+91 9876543210",
                email="membership@example.com",
            ),
            address=StoreAddress(
                address="11 Membership Road",
                city="Imphal",
                district="Imphal West",
                state="Manipur",
                country="India",
                postal_code="795001",
            ),
        )
    )
    return store.id


def _service(
    session: AsyncSession,
    events: RecordingPublisher,
) -> StoreMembershipService:
    memberships = SqlAlchemyStoreMembershipRepository(session)
    audit = MembershipAuditService(events)
    return StoreMembershipService(
        SqlAlchemyStoreRepository(session),
        memberships,
        StoreInvitationService(
            memberships,
            SqlAlchemyUserRepository(session),
            audit,
        ),
        MembershipLifecycleService(memberships, audit),
    )


async def test_invitation_creates_owner_and_prevents_duplicates(
    membership_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "membership-owner@example.com")
    staff_id = await _user(membership_session, "membership-staff@example.com")
    store_id = await _store(membership_session, events, owner_id)
    service = _service(membership_session, events)

    invited = await service.invite(
        store_id,
        owner_id,
        StoreMembershipInvitation(
            user_id=staff_id,
            role=StoreMembershipRole.STAFF,
        ),
    )

    assert invited.id.version == 7
    assert invited.status is StoreMembershipStatus.PENDING
    assert invited.invitation_expires_at is not None
    assert invited.invitation_expires_at > datetime.now(UTC)
    members, total = await service.list(
        store_id,
        owner_id,
        offset=0,
        limit=25,
    )
    assert total == 2
    owner = next(member for member in members if member.role == "owner")
    assert owner.user_id == owner_id
    assert owner.status is StoreMembershipStatus.ACTIVE
    assert [event.event_name for event in events.events][-1] == "store.member.invited"

    with pytest.raises(AppError) as duplicate:
        await service.invite(
            store_id,
            owner_id,
            StoreMembershipInvitation(
                user_id=staff_id,
                role=StoreMembershipRole.MANAGER,
            ),
        )
    assert duplicate.value.status_code == 409


async def test_accept_suspend_reactivate_change_role_and_remove(
    membership_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "lifecycle-owner@example.com")
    staff_id = await _user(membership_session, "lifecycle-staff@example.com")
    store_id = await _store(membership_session, events, owner_id)
    service = _service(membership_session, events)
    invited = await service.invite(
        store_id,
        owner_id,
        StoreMembershipInvitation(staff_id, StoreMembershipRole.STAFF),
    )

    accepted = await service.accept(
        store_id,
        invited.id,
        staff_id,
        invited.version,
    )
    assert accepted.status is StoreMembershipStatus.ACTIVE
    assert accepted.accepted_at is not None

    suspended = await service.update(
        store_id,
        accepted.id,
        owner_id,
        StoreMembershipUpdate(
            expected_version=accepted.version,
            status=StoreMembershipStatus.SUSPENDED,
        ),
    )
    assert suspended.status is StoreMembershipStatus.SUSPENDED

    reactivated = await service.update(
        store_id,
        suspended.id,
        owner_id,
        StoreMembershipUpdate(
            expected_version=suspended.version,
            status=StoreMembershipStatus.ACTIVE,
        ),
    )
    promoted = await service.update(
        store_id,
        reactivated.id,
        owner_id,
        StoreMembershipUpdate(
            expected_version=reactivated.version,
            role=StoreMembershipRole.MANAGER,
        ),
    )
    assert promoted.role is StoreMembershipRole.MANAGER

    await service.remove(store_id, promoted.id, owner_id)
    persisted = await SqlAlchemyStoreMembershipRepository(membership_session).get(
        store_id, promoted.id
    )
    assert persisted is not None
    assert persisted.status is StoreMembershipStatus.REMOVED
    assert persisted.removed_at is not None
    assert [event.event_name for event in events.events][-5:] == [
        "store.member.accepted",
        "store.member.suspended",
        "store.member.reactivated",
        "store.member.role_changed",
        "store.member.removed",
    ]


async def test_decline_invitee_boundary_and_stale_version(
    membership_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "decline-owner@example.com")
    staff_id = await _user(membership_session, "decline-staff@example.com")
    outsider_id = await _user(membership_session, "decline-outsider@example.com")
    store_id = await _store(membership_session, events, owner_id)
    service = _service(membership_session, events)
    invited = await service.invite(
        store_id,
        owner_id,
        StoreMembershipInvitation(staff_id, StoreMembershipRole.STAFF),
    )

    with pytest.raises(AppError) as hidden:
        await service.accept(store_id, invited.id, outsider_id, invited.version)
    assert hidden.value.status_code == 404

    with pytest.raises(AppError) as stale:
        await service.decline(store_id, invited.id, staff_id, invited.version + 1)
    assert stale.value.status_code == 409

    declined = await service.decline(
        store_id,
        invited.id,
        staff_id,
        invited.version,
    )
    assert declined.status is StoreMembershipStatus.DECLINED
    assert events.events[-1].event_name == "store.member.declined"


async def test_owner_membership_is_immutable_and_cross_store_access_is_hidden(
    membership_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "owner-immutable@example.com")
    other_owner_id = await _user(membership_session, "owner-other@example.com")
    store_id = await _store(membership_session, events, owner_id)
    service = _service(membership_session, events)
    members, _ = await service.list(store_id, owner_id, offset=0, limit=25)
    owner = next(member for member in members if member.role == "owner")

    with pytest.raises(AppError) as immutable:
        await service.remove(store_id, owner.id, owner_id)
    assert immutable.value.status_code == 409

    with pytest.raises(AppError) as hidden:
        await service.list(store_id, other_owner_id, offset=0, limit=25)
    assert hidden.value.status_code == 404


async def test_expired_invitation_cannot_be_accepted(
    membership_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "expiry-owner@example.com")
    staff_id = await _user(membership_session, "expiry-staff@example.com")
    store_id = await _store(membership_session, events, owner_id)
    memberships = SqlAlchemyStoreMembershipRepository(membership_session)
    invitation = await memberships.add_invitation(
        store_id=store_id,
        user_id=staff_id,
        role=StoreMembershipRole.STAFF,
        invited_by_id=owner_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service = _service(membership_session, events)

    with pytest.raises(AppError) as expired:
        await service.accept(
            store_id,
            invitation.id,
            staff_id,
            invitation.version,
        )
    assert expired.value.status_code == 409
    persisted = await memberships.get(store_id, invitation.id)
    assert persisted is not None
    assert persisted.status is StoreMembershipStatus.EXPIRED


async def test_membership_indexes_and_repository_counts(
    membership_session: AsyncSession,
    database_url: str,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(membership_session, "indexes-owner@example.com")
    store_id = await _store(membership_session, events, owner_id)
    service = _service(membership_session, events)
    await service.list(store_id, owner_id, offset=0, limit=25)
    assert (
        await SqlAlchemyStoreMembershipRepository(membership_session).count_current()
        >= 1
    )

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "store_memberships"
                )
            )
    finally:
        await engine.dispose()
    assert {index["name"] for index in indexes} >= {
        "ix_store_memberships_pending_expiry",
        "ix_store_memberships_store_status_created",
        "ix_store_memberships_user_status",
        "uq_store_memberships_active_owner",
        "uq_store_memberships_live_user",
        "uq_store_memberships_pending_user",
    }


def test_membership_metrics_are_low_cardinality() -> None:
    exposition = generate_latest().decode()
    for metric in (
        "fashion_network_store_members_total",
        "fashion_network_store_member_invitations_total",
        "fashion_network_store_member_acceptances_total",
        "fashion_network_store_member_removals_total",
    ):
        assert metric in exposition
        line = next(
            value for value in exposition.splitlines() if value.startswith(metric)
        )
        assert "{" not in line


def test_membership_openapi_documents_paths_and_permissions(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(membership_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)
    schema = application.openapi()
    base = "/api/v1/stores/{store_id}/members"
    expected = {
        ("post", base, "store:update"),
        ("get", base, "store:view"),
        ("patch", f"{base}/{{member_id}}", "store:update"),
        ("delete", f"{base}/{{member_id}}", "store:delete"),
        ("post", f"{base}/{{member_id}}/accept", "store:view"),
        ("post", f"{base}/{{member_id}}/decline", "store:view"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]


def test_membership_api_uses_permission_service_without_role_comparisons() -> None:
    owner_id = UUID(int=81)
    store_id = UUID(int=82)
    now = datetime.now(UTC)
    membership = StoreMembership(
        id=UUID(int=83),
        store_id=store_id,
        user_id=owner_id,
        role=StoreMembershipRole.OWNER,
        status=StoreMembershipStatus.ACTIVE,
        invited_by_id=owner_id,
        invitation_expires_at=None,
        accepted_at=now,
        removed_at=None,
        version=1,
        created_at=now,
        updated_at=now,
    )
    calls: list[str] = []

    class StubAuthorizationService:
        async def require_permission(
            self,
            principal: object,
            permission: str,
        ) -> None:
            del principal
            calls.append(permission)

    class StubMembershipService:
        async def list(
            self,
            requested_store_id: UUID,
            requested_owner_id: UUID,
            *,
            offset: int,
            limit: int,
        ) -> tuple[list[StoreMembership], int]:
            assert requested_store_id == store_id
            assert requested_owner_id == owner_id
            assert offset == 0
            assert limit == 25
            return [membership], 1

    identity = SimpleNamespace(
        user=SimpleNamespace(id=owner_id),
        session=SimpleNamespace(id=UUID(int=84)),
    )
    application = FastAPI()
    application.include_router(membership_router, prefix="/api/v1")
    application.dependency_overrides[current_identity_dependency] = lambda: identity
    application.dependency_overrides[authorization_service_dependency] = (
        StubAuthorizationService
    )
    application.dependency_overrides[store_membership_service_dependency] = (
        StubMembershipService
    )

    with TestClient(application) as client:
        response = client.get(f"/api/v1/stores/{store_id}/members")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(membership.id)
    assert calls == ["store:view"]
