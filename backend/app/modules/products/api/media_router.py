from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database.session import get_db
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.products.application.media_services import ProductMediaService
from app.modules.products.domain.media import ProductMediaRole
from app.modules.products.infrastructure.media_repositories import (
    ProductMediaRepository,
)
from app.modules.stores.infrastructure.media_storage import MinIOStorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)

router = APIRouter(prefix="/products/{product_id}/media", tags=["Product Media"])


async def product_media_dependency(
    request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> AsyncIterator[ProductMediaService]:
    settings = cast(Settings, request.app.state.settings)
    secret = (
        settings.s3_secret_access_key.get_secret_value()
        if settings.s3_secret_access_key
        else ""
    )
    if not settings.s3_access_key_id:
        raise RuntimeError("Product media storage is not configured.")
    storage = MinIOStorageProvider(
        settings.s3_endpoint_url,
        settings.s3_access_key_id,
        secret,
        region=settings.s3_region,
    )
    transaction = StoreMediaStorageTransaction(storage)
    service = ProductMediaService(
        ProductMediaRepository(session),
        storage,
        transaction,
        request.app.state.store_events,
        settings.s3_bucket,
        settings.media_presigned_url_expiration_seconds,
    )
    committed = False
    try:
        yield service
        await session.commit()
        committed = True
        await transaction.commit()
    except Exception:
        if not committed:
            await session.rollback()
            await transaction.rollback()
        raise


@router.post(
    "/primary",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
)
async def upload_primary(
    product_id: UUID,
    file: Annotated[UploadFile, File()],
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> object:
    return await service.upload(
        product_id,
        identity.user.id,
        ProductMediaRole.PRIMARY,
        file.filename or "upload",
        file.content_type or "",
        await file.read(),
    )


@router.post(
    "/gallery",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
)
async def upload_gallery(
    product_id: UUID,
    file: Annotated[UploadFile, File()],
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> object:
    return await service.upload(
        product_id,
        identity.user.id,
        ProductMediaRole.GALLERY,
        file.filename or "upload",
        file.content_type or "",
        await file.read(),
    )


@router.post(
    "/video",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
)
async def upload_video(
    product_id: UUID,
    file: Annotated[UploadFile, File()],
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> object:
    return await service.upload(
        product_id,
        identity.user.id,
        ProductMediaRole.GALLERY,
        file.filename or "upload.mp4",
        file.content_type or "video/mp4",
        await file.read(),
    )


@router.get("", dependencies=[require_permission("catalog:view")])
async def list_media(
    product_id: UUID,
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> object:
    return await service.list(product_id, identity.user.id)


@router.get("/{media_id}", dependencies=[require_permission("catalog:view")])
async def get_media(
    product_id: UUID,
    media_id: UUID,
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> object:
    media = await service.list(product_id, identity.user.id)
    for item in media:
        if item.id == media_id:
            return item
    raise RuntimeError("Media not found")


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:update")],
)
async def delete_media(
    product_id: UUID,
    media_id: UUID,
    version: int,
    identity: CurrentIdentity,
    service: Annotated[ProductMediaService, Depends(product_media_dependency)],
) -> None:
    await service.delete(product_id, media_id, identity.user.id, version)
