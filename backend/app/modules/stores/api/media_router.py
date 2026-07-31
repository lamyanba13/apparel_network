from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.stores.api.dependencies import StoreMediaServiceDependency
from app.modules.stores.api.media_schemas import (
    StoreMediaListResponse,
    StoreMediaReorderRequest,
    StoreMediaResponse,
    StoreMediaUpdateRequest,
)
from app.modules.stores.application.media_schemas import (
    StoreMediaReorderItem,
    StoreMediaUpdate,
    StoreMediaUpload,
)
from app.modules.stores.application.media_validation import (
    StoreMediaValidationService,
)
from app.modules.stores.domain import StoreMedia, StoreMediaType

router = APIRouter(
    prefix="/stores/{store_id}/media",
    tags=["Store Media"],
)

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Store permission"},
}
_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    404: {"description": "Store or Store media not found"},
}
_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESOURCE_RESPONSES,
    409: {"description": "Duplicate media, stale version, or lifecycle conflict"},
    422: {"description": "The image or metadata failed validation"},
    503: {"description": "Object storage is unavailable"},
}


async def _response(
    media: StoreMedia,
    service: StoreMediaServiceDependency,
) -> StoreMediaResponse:
    download_url, expires_at = await service.generate_download_url(media)
    return StoreMediaResponse(
        id=media.id,
        store_id=media.store_id,
        uploaded_by_id=media.uploaded_by_id,
        media_type=media.media_type,
        status=media.status,
        original_filename=media.original_filename,
        extension=media.extension,
        mime_type=media.mime_type,
        file_size=media.file_size,
        width=media.width,
        height=media.height,
        orientation=media.orientation,
        aspect_ratio=media.aspect_ratio,
        display_order=media.display_order,
        is_public=media.is_public,
        created_at=media.created_at,
        updated_at=media.updated_at,
        version=media.version,
        download_url=download_url,
        download_url_expires_at=expires_at,
    )


async def _upload(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
    media_type: StoreMediaType,
    file: UploadFile,
    checksum_sha256: str | None,
    display_order: int,
    is_public: bool,
) -> StoreMediaResponse:
    maximum = StoreMediaValidationService().maximum_size(media_type)
    data = await file.read(maximum + 1)
    media = await service.upload(
        store_id,
        identity.user.id,
        media_type,
        StoreMediaUpload(
            filename=file.filename or "",
            declared_mime_type=file.content_type or "",
            data=data,
            declared_checksum_sha256=checksum_sha256,
            display_order=display_order,
            is_public=is_public,
        ),
    )
    return await _response(media, service)


@router.post(
    "/logo",
    response_model=StoreMediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload or replace the Store logo",
    description=(
        "Validates and stores a JPEG, PNG, WebP, or AVIF logo. A prior active "
        "logo is archived atomically with the metadata change."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def upload_store_logo(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
    file: Annotated[UploadFile, File(description="Store logo image")],
    checksum_sha256: Annotated[str | None, Form()] = None,
    is_public: Annotated[bool, Form()] = False,
) -> StoreMediaResponse:
    return await _upload(
        store_id,
        identity,
        service,
        StoreMediaType.LOGO,
        file,
        checksum_sha256,
        0,
        is_public,
    )


@router.post(
    "/banner",
    response_model=StoreMediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload or replace the Store banner",
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def upload_store_banner(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
    file: Annotated[UploadFile, File(description="Store banner image")],
    checksum_sha256: Annotated[str | None, Form()] = None,
    is_public: Annotated[bool, Form()] = False,
) -> StoreMediaResponse:
    return await _upload(
        store_id,
        identity,
        service,
        StoreMediaType.BANNER,
        file,
        checksum_sha256,
        0,
        is_public,
    )


@router.post(
    "/gallery",
    response_model=StoreMediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a Store gallery image",
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def upload_store_gallery(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
    file: Annotated[UploadFile, File(description="Store gallery image")],
    checksum_sha256: Annotated[str | None, Form()] = None,
    display_order: Annotated[int, Form(ge=0)] = 0,
    is_public: Annotated[bool, Form()] = False,
) -> StoreMediaResponse:
    return await _upload(
        store_id,
        identity,
        service,
        StoreMediaType.GALLERY,
        file,
        checksum_sha256,
        display_order,
        is_public,
    )


@router.get(
    "",
    response_model=StoreMediaListResponse,
    summary="List Store media",
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def list_store_media(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StoreMediaListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    media, total = await service.list(
        store_id,
        identity.user.id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return StoreMediaListResponse(
        items=[await _response(item, service) for item in media],
        page=PageMetadata(
            has_more=pagination.offset + len(media) < total,
            limit=pagination.limit,
            total=total,
            offset=pagination.offset,
        ),
    )


@router.post(
    "/reorder",
    response_model=list[StoreMediaResponse],
    summary="Reorder Store gallery images",
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def reorder_store_gallery(
    store_id: UUID,
    payload: StoreMediaReorderRequest,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
) -> list[StoreMediaResponse]:
    reordered = await service.reorder(
        store_id,
        identity.user.id,
        [
            StoreMediaReorderItem(
                media_id=item.media_id,
                display_order=item.display_order,
                expected_version=item.version,
            )
            for item in payload.items
        ],
    )
    return [await _response(item, service) for item in reordered]


@router.get(
    "/{media_id}",
    response_model=StoreMediaResponse,
    summary="Get Store media",
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def get_store_media(
    store_id: UUID,
    media_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
) -> StoreMediaResponse:
    media = await service.get(store_id, media_id, identity.user.id)
    return await _response(media, service)


@router.patch(
    "/{media_id}",
    response_model=StoreMediaResponse,
    summary="Update Store media metadata",
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def update_store_media(
    store_id: UUID,
    media_id: UUID,
    payload: StoreMediaUpdateRequest,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
) -> StoreMediaResponse:
    media = await service.update(
        store_id,
        media_id,
        identity.user.id,
        StoreMediaUpdate(
            expected_version=payload.version,
            display_order=payload.display_order,
            is_public=payload.is_public,
        ),
    )
    return await _response(media, service)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete Store media",
    dependencies=[require_permission("store:delete")],
    responses=_MUTATION_RESPONSES,
)
async def delete_store_media(
    store_id: UUID,
    media_id: UUID,
    identity: CurrentIdentity,
    service: StoreMediaServiceDependency,
) -> Response:
    await service.delete(store_id, media_id, identity.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
