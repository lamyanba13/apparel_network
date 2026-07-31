from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.core.config import Settings
from app.database.session import get_db
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyUserRepository,
)
from app.modules.stores.application.media_services import (
    StoreMediaAuditService,
    StoreMediaService,
)
from app.modules.stores.application.media_storage import StorageProvider
from app.modules.stores.application.media_validation import (
    StoreMediaValidationService,
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
from app.modules.stores.infrastructure.media_storage import MinIOStorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)
from app.modules.stores.infrastructure.persistence.media_repositories import (
    SqlAlchemyStoreMediaRepository,
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


async def store_media_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[StoreMediaService]:
    settings = cast(Settings, request.app.state.settings)
    secret = (
        settings.s3_secret_access_key.get_secret_value()
        if settings.s3_secret_access_key is not None
        else ""
    )
    if not settings.s3_access_key_id or not secret:
        raise AppError(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            title="Store media unavailable",
            detail="Store media storage is not configured.",
            status_code=503,
        )
    storage: StorageProvider = MinIOStorageProvider(
        settings.s3_endpoint_url,
        settings.s3_access_key_id,
        secret,
        region=settings.s3_region,
    )
    storage_transaction = StoreMediaStorageTransaction(storage)
    events = cast(EventPublisher, request.app.state.store_events)
    committed = False
    try:
        yield StoreMediaService(
            SqlAlchemyStoreRepository(session),
            SqlAlchemyStoreMediaRepository(session),
            storage,
            storage_transaction,
            StoreMediaValidationService(),
            StoreMediaAuditService(events),
            bucket=settings.s3_bucket,
            presigned_expiration_seconds=(
                settings.media_presigned_url_expiration_seconds
            ),
        )
        await session.commit()
        committed = True
        await storage_transaction.commit()
    except Exception:
        if not committed:
            await session.rollback()
            await storage_transaction.rollback()
        raise


StoreMediaServiceDependency = Annotated[
    StoreMediaService,
    Depends(store_media_service_dependency),
]
