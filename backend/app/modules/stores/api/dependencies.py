from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyUserRepository,
)
from app.modules.stores.application.membership_services import (
    MembershipAuditService,
    MembershipLifecycleService,
    StoreInvitationService,
    StoreMembershipService,
)
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.application.verification_services import (
    StoreVerificationService,
    VerificationAuditService,
    VerificationLifecycleService,
    VerificationPolicyService,
)
from app.modules.stores.infrastructure.persistence.membership_repositories import (
    SqlAlchemyStoreMembershipRepository,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)
from app.modules.stores.infrastructure.persistence.verification_repositories import (
    SqlAlchemyStoreVerificationRepository,
)


async def store_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[StoreService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield StoreService(
            SqlAlchemyStoreRepository(session),
            events,
            StoreValidationService(),
            StoreSlugService(),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


StoreServiceDependency = Annotated[
    StoreService,
    Depends(store_service_dependency),
]


async def store_verification_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[StoreVerificationService]:
    events = cast(EventPublisher, request.app.state.store_events)
    stores = SqlAlchemyStoreRepository(session)
    verifications = SqlAlchemyStoreVerificationRepository(session)
    policy = VerificationPolicyService()
    try:
        yield StoreVerificationService(
            stores,
            verifications,
            VerificationLifecycleService(
                verifications,
                stores,
                policy,
                VerificationAuditService(events),
            ),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


StoreVerificationServiceDependency = Annotated[
    StoreVerificationService,
    Depends(store_verification_service_dependency),
]


async def store_membership_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[StoreMembershipService]:
    events = cast(EventPublisher, request.app.state.store_events)
    stores = SqlAlchemyStoreRepository(session)
    memberships = SqlAlchemyStoreMembershipRepository(session)
    audit = MembershipAuditService(events)
    try:
        yield StoreMembershipService(
            stores,
            memberships,
            StoreInvitationService(
                memberships,
                SqlAlchemyUserRepository(session),
                audit,
            ),
            MembershipLifecycleService(memberships, audit),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


StoreMembershipServiceDependency = Annotated[
    StoreMembershipService,
    Depends(store_membership_service_dependency),
]
