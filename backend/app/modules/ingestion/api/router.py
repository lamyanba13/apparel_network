from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.common.api.dependencies import idempotency_key_dependency
from app.common.idempotency import IdempotencyKey
from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.ingestion.api.dependencies import CatalogImportServiceDependency
from app.modules.ingestion.api.schemas import (
    CatalogImportCreateRequest,
    CatalogImportErrorListResponse,
    CatalogImportErrorResponse,
    CatalogImportListResponse,
    CatalogImportMediaResponse,
    CatalogImportPreviewResponse,
    CatalogImportResponse,
    CatalogImportRowResponse,
    CatalogImportRowsResponse,
)
from app.modules.ingestion.application.schemas import (
    CatalogImportCreate,
    CatalogImportFilter,
)
from app.modules.ingestion.domain import ImportSourceType, ImportStatus

router = APIRouter(prefix="/catalog-imports", tags=["Catalog Imports"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Catalog permission"},
    404: {"description": "Catalog Import not found or inaccessible"},
}


@router.post(
    "",
    response_model=CatalogImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Idempotency conflict"}},
)
async def create_catalog_import(
    payload: CatalogImportCreateRequest,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
    response: Response,
    idempotency_key: Annotated[IdempotencyKey, Depends(idempotency_key_dependency)],
) -> CatalogImportResponse:
    value = await service.create(
        CatalogImportCreate(
            store_id=payload.store_id,
            catalog_id=payload.catalog_id,
            actor_id=identity.user.id,
            source_type=payload.source_type,
            idempotency_key=idempotency_key.value,
        )
    )
    response.headers["Location"] = f"/api/v1/catalog-imports/{value.id}"
    return CatalogImportResponse.model_validate(value)


@router.post(
    "/{import_id}/spreadsheet",
    response_model=CatalogImportResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Import lifecycle conflict"}},
)
async def upload_spreadsheet(
    import_id: UUID,
    file: Annotated[UploadFile, File()],
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportResponse:
    value = await service.upload_spreadsheet(
        import_id,
        identity.user.id,
        file.filename or "catalog.csv",
        file.content_type or "application/octet-stream",
        await file.read(),
    )
    return CatalogImportResponse.model_validate(value)


@router.post(
    "/{import_id}/media",
    response_model=CatalogImportMediaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Duplicate Import image"}},
)
async def upload_import_media(
    import_id: UUID,
    file: Annotated[UploadFile, File()],
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportMediaResponse:
    value = await service.upload_media(
        import_id,
        identity.user.id,
        file.filename or "image",
        file.content_type or "",
        await file.read(),
    )
    return CatalogImportMediaResponse.model_validate(value)


@router.post(
    "/{import_id}/validate",
    response_model=CatalogImportPreviewResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Import lifecycle conflict"}},
)
async def validate_catalog_import(
    import_id: UUID,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportPreviewResponse:
    value, preview = await service.validate(import_id, identity.user.id)
    return CatalogImportPreviewResponse(
        catalog_import=CatalogImportResponse.model_validate(value),
        total_rows=preview.total_rows,
        valid_rows=preview.valid_rows,
        invalid_rows=preview.invalid_rows,
        error_count=preview.error_count,
        warning_count=preview.warning_count,
    )


@router.post(
    "/{import_id}/commit",
    response_model=CatalogImportResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Import or canonical conflict"}},
)
async def commit_catalog_import(
    import_id: UUID,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportResponse:
    value = await service.commit(import_id, identity.user.id)
    return CatalogImportResponse.model_validate(value)


@router.get(
    "",
    response_model=CatalogImportListResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_catalog_imports(
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
    store_id: UUID | None = None,
    status_filter: Annotated[ImportStatus | None, Query(alias="status")] = None,
    source_type: ImportSourceType | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CatalogImportListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_imports(
        identity.user.id,
        CatalogImportFilter(store_id, status_filter, source_type, offset, limit),
    )
    return CatalogImportListResponse(
        items=[CatalogImportResponse.model_validate(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{import_id}",
    response_model=CatalogImportResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def get_catalog_import(
    import_id: UUID,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportResponse:
    return CatalogImportResponse.model_validate(
        await service.get(import_id, identity.user.id)
    )


@router.get(
    "/{import_id}/rows",
    response_model=CatalogImportRowsResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_catalog_import_rows(
    import_id: UUID,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
) -> CatalogImportRowsResponse:
    values = await service.rows(import_id, identity.user.id)
    return CatalogImportRowsResponse(
        items=[CatalogImportRowResponse.model_validate(value) for value in values]
    )


@router.get(
    "/{import_id}/errors",
    response_model=CatalogImportErrorListResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_catalog_import_errors(
    import_id: UUID,
    identity: CurrentIdentity,
    service: CatalogImportServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CatalogImportErrorListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.errors(
        import_id, identity.user.id, offset=offset, limit=limit
    )
    return CatalogImportErrorListResponse(
        items=[CatalogImportErrorResponse.model_validate(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )
