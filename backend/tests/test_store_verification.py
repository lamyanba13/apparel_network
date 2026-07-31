from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
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
from app.modules.stores.api.dependencies import (
    store_verification_service_dependency,
)
from app.modules.stores.api.verification_router import (
    router as store_verification_router,
)
from app.modules.stores.application.schemas import StoreCreate
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.application.verification_schemas import (
    StoreVerificationApproval,
    StoreVerificationRejection,
    StoreVerificationReview,
    StoreVerificationSubmission,
)
from app.modules.stores.application.verification_services import (
    StoreVerificationService,
    VerificationAuditService,
    VerificationLifecycleService,
    VerificationPolicyService,
)
from app.modules.stores.domain import (
    StoreAddress,
    StoreContact,
    StoreStatus,
    StoreVerification,
    StoreVerificationMetadata,
    StoreVerificationStatus,
    VerificationStatus,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)
from app.modules.stores.infrastructure.persistence.verification_models import (
    StoreVerificationModel,
)
from app.modules.stores.infrastructure.persistence.verification_repositories import (
    SqlAlchemyStoreVerificationRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@pytest.fixture
def migrated_verification_database(
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
async def verification_session(
    migrated_verification_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_verification_database
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
            display_name="Verification Actor",
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
            name="Verification Store",
            description=None,
            contact=StoreContact(
                phone="+91 9876543210",
                email="verification@example.com",
            ),
            address=StoreAddress(
                address="10 Review Road",
                city="Imphal",
                district="Imphal West",
                state="Manipur",
                country="India",
                postal_code="795001",
            ),
        )
    )
    return store.id


def _verification_service(
    session: AsyncSession,
    events: RecordingPublisher,
) -> StoreVerificationService:
    stores = SqlAlchemyStoreRepository(session)
    verifications = SqlAlchemyStoreVerificationRepository(session)
    return StoreVerificationService(
        stores,
        verifications,
        VerificationLifecycleService(
            verifications,
            stores,
            VerificationPolicyService(),
            VerificationAuditService(events),
        ),
    )


def _submission(
    license_number: str = "MN-BUSINESS-2026-001",
) -> StoreVerificationSubmission:
    return StoreVerificationSubmission(
        metadata=StoreVerificationMetadata(
            business_license=license_number,
            tax_registration="14ABCDE1234F1Z5",
            owner_identity="Government identity checked",
            address_proof="Municipal utility record",
            additional_notes="Registered trading name supplied.",
        )
    )


async def test_submission_is_persisted_atomic_owner_scoped_and_idempotent(
    verification_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(verification_session, "owner-verify@example.com")
    other_id = await _user(verification_session, "other-verify@example.com")
    store_id = await _store(verification_session, events, owner_id)
    service = _verification_service(verification_session, events)

    submitted = await service.submit(store_id, owner_id, _submission())

    assert submitted.id.version == 7
    assert submitted.status is StoreVerificationStatus.SUBMITTED
    assert submitted.submitted_by_id == owner_id
    assert submitted.reviewed_by_id is None
    assert submitted.version == 1
    assert events.events[-1].event_name == "store.verification.submitted"
    assert verification_session.in_transaction()

    repeated = await service.submit(store_id, owner_id, _submission())
    assert repeated.id == submitted.id
    assert repeated.version == submitted.version

    store = await SqlAlchemyStoreRepository(verification_session).get_by_id(store_id)
    assert store is not None
    assert store.status is StoreStatus.PENDING_REVIEW
    assert store.verification_status is VerificationStatus.PENDING

    with pytest.raises(AppError) as concealed:
        await service.get_owned(store_id, other_id)
    assert concealed.value.status_code == 404


async def test_review_and_approval_are_atomic_and_emit_events(
    verification_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(verification_session, "approve-owner@example.com")
    reviewer_id = await _user(verification_session, "approve-admin@example.com")
    store_id = await _store(verification_session, events, owner_id)
    service = _verification_service(verification_session, events)
    submitted = await service.submit(store_id, owner_id, _submission())

    review = await service.review(
        store_id,
        reviewer_id,
        StoreVerificationReview(
            expected_version=submitted.version,
            review_notes="References checked.",
        ),
    )
    assert review.status is StoreVerificationStatus.IN_REVIEW
    assert review.reviewed_by_id == reviewer_id
    assert review.review_started_at is not None
    assert events.events[-1].event_name == "store.verification.started"

    approved = await service.approve(
        store_id,
        reviewer_id,
        StoreVerificationApproval(expected_version=review.version),
    )
    assert approved.status is StoreVerificationStatus.APPROVED
    assert approved.reviewed_at is not None
    assert events.events[-1].event_name == "store.verified"
    assert events.events[-1].payload["actor_user_id"] == str(reviewer_id)

    store = await SqlAlchemyStoreRepository(verification_session).get_by_id(store_id)
    assert store is not None
    assert store.status is StoreStatus.ACTIVE
    assert store.verification_status is VerificationStatus.VERIFIED

    repeated = await service.approve(
        store_id,
        reviewer_id,
        StoreVerificationApproval(expected_version=1),
    )
    assert repeated.id == approved.id
    assert repeated.version == approved.version


async def test_rejection_can_be_reopened_and_preserves_one_record(
    verification_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(verification_session, "reopen-owner@example.com")
    reviewer_id = await _user(verification_session, "reopen-admin@example.com")
    store_id = await _store(verification_session, events, owner_id)
    service = _verification_service(verification_session, events)
    submitted = await service.submit(store_id, owner_id, _submission())
    review = await service.review(
        store_id,
        reviewer_id,
        StoreVerificationReview(expected_version=submitted.version),
    )

    rejected = await service.reject(
        store_id,
        reviewer_id,
        StoreVerificationRejection(
            expected_version=review.version,
            rejection_reason=" Address reference does not match. ",
            review_notes="Request a current municipal reference.",
        ),
    )
    assert rejected.status is StoreVerificationStatus.REJECTED
    assert rejected.rejection_reason == "Address reference does not match."
    assert events.events[-1].event_name == "store.verification.rejected"

    store = await SqlAlchemyStoreRepository(verification_session).get_by_id(store_id)
    assert store is not None
    assert store.status is StoreStatus.DRAFT
    assert store.verification_status is VerificationStatus.REJECTED

    reopened = await service.submit(
        store_id,
        owner_id,
        _submission("MN-BUSINESS-2026-002"),
    )
    assert reopened.id == rejected.id
    assert reopened.status is StoreVerificationStatus.SUBMITTED
    assert reopened.rejection_reason is None
    assert reopened.reviewed_by_id is None
    assert events.events[-1].event_name == "store.verification.reopened"


async def test_invalid_transitions_and_stale_versions_are_rejected(
    verification_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(verification_session, "invalid-owner@example.com")
    reviewer_id = await _user(verification_session, "invalid-admin@example.com")
    store_id = await _store(verification_session, events, owner_id)
    service = _verification_service(verification_session, events)
    submitted = await service.submit(store_id, owner_id, _submission())

    with pytest.raises(AppError) as premature:
        await service.approve(
            store_id,
            reviewer_id,
            StoreVerificationApproval(expected_version=submitted.version),
        )
    assert premature.value.status_code == 409

    with pytest.raises(AppError) as stale:
        await service.review(
            store_id,
            reviewer_id,
            StoreVerificationReview(expected_version=999),
        )
    assert stale.value.status_code == 409

    with pytest.raises(AppError) as missing_evidence:
        await service.submit(
            store_id,
            owner_id,
            StoreVerificationSubmission(metadata=StoreVerificationMetadata()),
        )
    assert missing_evidence.value.status_code == 422


async def test_repository_constraints_and_indexes(
    verification_session: AsyncSession,
    database_url: str,
) -> None:
    events = RecordingPublisher()
    owner_id = await _user(verification_session, "constraints-owner@example.com")
    store_id = await _store(verification_session, events, owner_id)
    repository = SqlAlchemyStoreVerificationRepository(verification_session)
    submitted = await repository.add(
        store_id=store_id,
        submitted_by_id=owner_id,
        metadata=_submission().metadata,
        submitted_at=datetime.now(UTC),
    )
    verification_session.add(
        StoreVerificationModel(
            store_id=store_id,
            submitted_by_id=owner_id,
            status=StoreVerificationStatus.SUBMITTED,
            submitted_at=datetime.now(UTC),
            business_license="DUPLICATE",
        )
    )
    with pytest.raises(IntegrityError):
        await verification_session.flush()
    await verification_session.rollback()

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "store_verifications"
                )
            )
    finally:
        await engine.dispose()
    assert submitted.id.version == 7
    assert {index["name"] for index in indexes} >= {
        "ix_store_verifications_pending",
        "ix_store_verifications_reviewed_by_status",
        "ix_store_verifications_status_submitted_at",
    }


def test_verification_metrics_are_low_cardinality() -> None:
    exposition = generate_latest().decode()
    for metric in (
        "fashion_network_store_verification_submitted_total",
        "fashion_network_store_verification_approved_total",
        "fashion_network_store_verification_rejected_total",
        "fashion_network_store_verification_pending_total",
    ):
        assert metric in exposition
        line = next(
            value for value in exposition.splitlines() if value.startswith(metric)
        )
        assert "{" not in line


def test_verification_openapi_documents_paths_and_permissions(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(store_verification_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)
    schema = application.openapi()
    base = "/api/v1/stores/{store_id}/verification"
    expected = {
        ("post", f"{base}/submit", "store:update"),
        ("get", base, "store:view"),
        ("patch", f"{base}/review", "admin:access"),
        ("post", f"{base}/approve", "admin:access"),
        ("post", f"{base}/reject", "admin:access"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
        if method != "get":
            assert (
                "application/problem+json" in operation["responses"]["409"]["content"]
            )


def test_verification_api_uses_permission_service_without_role_comparisons() -> None:
    owner_id = UUID(int=71)
    store_id = UUID(int=72)
    calls: list[str] = []
    now = datetime.now(UTC)
    verification = StoreVerification(
        id=UUID(int=73),
        store_id=store_id,
        submitted_by_id=owner_id,
        reviewed_by_id=UUID(int=75),
        status=StoreVerificationStatus.REJECTED,
        submitted_at=now,
        review_started_at=now,
        reviewed_at=now,
        rejection_reason="Address reference must be updated.",
        review_notes="Private administrative review notes.",
        metadata=StoreVerificationMetadata(business_license="LICENSE"),
        version=1,
        created_at=now,
        updated_at=now,
    )

    class StubAuthorizationService:
        async def require_permission(
            self,
            identity: object,
            permission: str,
        ) -> None:
            del identity
            calls.append(permission)

    class StubVerificationService:
        async def get_owned(
            self,
            requested_store_id: UUID,
            requested_owner_id: UUID,
        ) -> StoreVerification:
            assert requested_store_id == store_id
            assert requested_owner_id == owner_id
            return verification

    identity = SimpleNamespace(
        user=SimpleNamespace(id=owner_id),
        session=SimpleNamespace(id=UUID(int=74)),
    )
    application = FastAPI()
    application.include_router(store_verification_router, prefix="/api/v1")
    application.dependency_overrides[current_identity_dependency] = lambda: identity
    application.dependency_overrides[authorization_service_dependency] = (
        StubAuthorizationService
    )
    application.dependency_overrides[store_verification_service_dependency] = (
        StubVerificationService
    )

    with TestClient(application) as client:
        response = client.get(f"/api/v1/stores/{store_id}/verification")

    assert response.status_code == 200
    assert response.json()["id"] == str(verification.id)
    assert response.json()["reviewed_by_id"] is None
    assert response.json()["review_notes"] is None
    assert response.json()["rejection_reason"] == verification.rejection_reason
    assert calls == ["store:view"]
