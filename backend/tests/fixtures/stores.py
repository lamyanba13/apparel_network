from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import DomainEvent
from app.modules.identity.application.schemas import UserRecord
from app.modules.stores.application.schemas import StoreCreate
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.application.verification_schemas import (
    StoreVerificationApproval,
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
    Store,
    StoreAddress,
    StoreContact,
    StoreVerificationMetadata,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)
from app.modules.stores.infrastructure.persistence.verification_repositories import (
    SqlAlchemyStoreVerificationRepository,
)
from tests.fixtures.identity import create_user
from tests.helpers.builders import email, store_name


class _DiscardingEventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        del event


def _store_service(session: AsyncSession) -> StoreService:
    return StoreService(
        SqlAlchemyStoreRepository(session),
        _DiscardingEventPublisher(),
        StoreValidationService(),
        StoreSlugService(),
    )


def _verification_service(session: AsyncSession) -> StoreVerificationService:
    stores = SqlAlchemyStoreRepository(session)
    verifications = SqlAlchemyStoreVerificationRepository(session)
    return StoreVerificationService(
        stores,
        verifications,
        VerificationLifecycleService(
            verifications,
            stores,
            VerificationPolicyService(),
            VerificationAuditService(_DiscardingEventPublisher()),
        ),
    )


async def create_store(
    session: AsyncSession,
    owner_id: UUID,
    value: int = 1,
) -> Store:
    return await _store_service(session).create(
        StoreCreate(
            owner_id=owner_id,
            name=store_name(value),
            description=f"Integration test store {value}",
            contact=StoreContact(
                phone=f"+91 987650{value:04d}",
                email=email(value),
            ),
            address=StoreAddress(
                address=f"{value} Test Market Road",
                city="Imphal",
                district="Imphal West",
                state="Manipur",
                country="India",
                postal_code="795001",
            ),
        )
    )


async def verify_store(
    session: AsyncSession,
    store: Store,
    reviewer_id: UUID,
) -> Store:
    service = _verification_service(session)
    submitted = await service.submit(
        store.id,
        store.owner_id,
        StoreVerificationSubmission(
            metadata=StoreVerificationMetadata(
                business_license=f"TEST-LICENSE-{store.id}",
                address_proof="Integration test address proof",
            )
        ),
    )
    review = await service.review(
        store.id,
        reviewer_id,
        StoreVerificationReview(expected_version=submitted.version),
    )
    await service.approve(
        store.id,
        reviewer_id,
        StoreVerificationApproval(expected_version=review.version),
    )
    verified = await SqlAlchemyStoreRepository(session).get_by_id(store.id)
    assert verified is not None
    return verified


@pytest.fixture
async def store(db_session: AsyncSession, identity_user: UserRecord) -> Store:
    return await create_store(db_session, identity_user.id)


@pytest.fixture
async def verified_store(db_session: AsyncSession, store: Store) -> Store:
    reviewer = await create_user(db_session, value=2)
    return await verify_store(db_session, store, reviewer.id)
