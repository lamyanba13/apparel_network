from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.catalogs.api.dependencies import CatalogServiceDependency
from app.modules.catalogs.api.schemas import (
    CatalogCreateRequest,
    CatalogListResponse,
    CatalogResponse,
    CatalogUpdateRequest,
)
from app.modules.catalogs.application.schemas import CatalogCreate, CatalogUpdate
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity

router = APIRouter(prefix="/catalogs", tags=["Catalogs"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Catalog permission"},
    404: {"description": "Catalog not found or not owned by this identity"},
}


def _response(catalog: Any) -> CatalogResponse:
    return CatalogResponse.model_validate(catalog, from_attributes=True)


@router.post(
    "",
    response_model=CatalogResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:create")],
    responses={**_RESPONSES, 409: {"description": "Catalog slug conflict"}},
)
async def create_catalog(
    payload: CatalogCreateRequest,
    identity: CurrentIdentity,
    service: CatalogServiceDependency,
    response: Response,
) -> CatalogResponse:
    catalog = await service.create(
        CatalogCreate(
            store_id=payload.store_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            status=payload.status,
            visibility=payload.visibility,
            sort_order=payload.sort_order,
            actor_id=identity.user.id,
            is_default=payload.is_default,
        )
    )
    response.headers["Location"] = f"/api/v1/catalogs/{catalog.id}"
    return _response(catalog)


@router.get(
    "",
    response_model=CatalogListResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_catalogs(
    identity: CurrentIdentity,
    service: CatalogServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CatalogListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    items, total = await service.list_owned(
        identity.user.id, offset=offset, limit=limit
    )
    return CatalogListResponse(
        items=[_response(item) for item in items],
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{catalog_id}",
    response_model=CatalogResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def get_catalog(
    catalog_id: UUID, identity: CurrentIdentity, service: CatalogServiceDependency
) -> CatalogResponse:
    return _response(await service.get_owned(catalog_id, identity.user.id))


@router.patch(
    "/{catalog_id}",
    response_model=CatalogResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_catalog(
    catalog_id: UUID,
    payload: CatalogUpdateRequest,
    identity: CurrentIdentity,
    service: CatalogServiceDependency,
) -> CatalogResponse:
    return _response(
        await service.update_owned(
            catalog_id,
            identity.user.id,
            CatalogUpdate(
                values=payload.model_dump(exclude={"version"}, exclude_unset=True),
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.delete(
    "/{catalog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_catalog(
    catalog_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: CatalogServiceDependency,
) -> Response:
    await service.delete_owned(catalog_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
