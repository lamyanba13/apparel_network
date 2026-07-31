from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.stores.api.dependencies import StoreServiceDependency
from app.modules.stores.api.schemas import (
    StoreCreateRequest,
    StoreListResponse,
    StoreResponse,
    StoreUpdateRequest,
)
from app.modules.stores.application.schemas import StoreCreate, StoreUpdate
from app.modules.stores.domain import Store, StoreAddress, StoreContact

router = APIRouter(prefix="/stores", tags=["Stores"])

_AUTH_RESPONSE: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Store permission"},
}
_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSE,
    404: {"description": "Store not found or not owned by this identity"},
}


def _response(store: Store) -> StoreResponse:
    return StoreResponse(
        id=store.id,
        owner_id=store.owner_id,
        name=store.name,
        slug=store.slug,
        description=store.description,
        phone=store.contact.phone,
        email=store.contact.email,
        website=store.contact.website,
        address=store.address.address,
        city=store.address.city,
        district=store.address.district,
        state=store.address.state,
        country=store.address.country,
        postal_code=store.address.postal_code,
        latitude=store.address.latitude,
        longitude=store.address.longitude,
        logo_url=store.logo_url,
        banner_url=store.banner_url,
        status=store.status,
        verification_status=store.verification_status,
        created_at=store.created_at,
        updated_at=store.updated_at,
        version=store.version,
    )


@router.post(
    "",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Store profile",
    description=(
        "Creates a draft Store owned by the authenticated identity. The slug "
        "and lifecycle states are server-managed."
    ),
    dependencies=[require_permission("store:create")],
    responses={**_AUTH_RESPONSE, 409: {"description": "Store slug conflict"}},
)
async def create_store(
    payload: StoreCreateRequest,
    identity: CurrentIdentity,
    service: StoreServiceDependency,
    response: Response,
) -> StoreResponse:
    store = await service.create(
        StoreCreate(
            owner_id=identity.user.id,
            name=payload.name,
            description=payload.description,
            contact=StoreContact(
                phone=payload.phone,
                email=payload.email,
                website=payload.website,
            ),
            address=StoreAddress(
                address=payload.address,
                city=payload.city,
                district=payload.district,
                state=payload.state,
                country=payload.country,
                postal_code=payload.postal_code,
                latitude=payload.latitude,
                longitude=payload.longitude,
            ),
            logo_url=payload.logo_url,
            banner_url=payload.banner_url,
        )
    )
    response.headers["Location"] = f"/api/v1/stores/{store.id}"
    return _response(store)


@router.get(
    "",
    response_model=StoreListResponse,
    summary="List owned Stores",
    description=(
        "Returns a bounded list of non-deleted Stores owned by the "
        "authenticated identity."
    ),
    dependencies=[require_permission("store:view")],
    responses=_AUTH_RESPONSE,
)
async def list_stores(
    identity: CurrentIdentity,
    service: StoreServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StoreListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    stores, total = await service.list_owned(
        identity.user.id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return StoreListResponse(
        items=[_response(store) for store in stores],
        page=PageMetadata(
            has_more=pagination.offset + len(stores) < total,
            limit=pagination.limit,
            total=total,
            offset=pagination.offset,
        ),
    )


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get an owned Store",
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def get_store(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreServiceDependency,
) -> StoreResponse:
    return _response(await service.get_owned(store_id, identity.user.id))


@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Update an owned Store",
    description=(
        "Applies owner-editable fields using the submitted optimistic version. "
        "Lifecycle, verification, ownership, and slug are server-managed."
    ),
    dependencies=[require_permission("store:update")],
    responses={
        **_RESOURCE_RESPONSES,
        409: {"description": "The submitted version is stale"},
    },
)
async def update_store(
    store_id: UUID,
    payload: StoreUpdateRequest,
    identity: CurrentIdentity,
    service: StoreServiceDependency,
) -> StoreResponse:
    changes = payload.model_dump(
        exclude={"version"},
        exclude_unset=True,
    )
    store = await service.update_owned(
        store_id,
        identity.user.id,
        StoreUpdate(
            values=changes,
            expected_version=payload.version,
        ),
    )
    return _response(store)


@router.delete(
    "/{store_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Close an owned Store",
    description=(
        "Closes and soft-deletes the Store. Historical data remains retained."
    ),
    dependencies=[require_permission("store:delete")],
    responses=_RESOURCE_RESPONSES,
)
async def delete_store(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreServiceDependency,
) -> Response:
    await service.delete_owned(store_id, identity.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
