from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.pagination import PageMetadata
from app.modules.ingestion.domain import (
    ImportErrorSeverity,
    ImportRowAction,
    ImportRowStatus,
    ImportSourceType,
    ImportStatus,
)


class CatalogImportCreateRequest(BaseModel):
    store_id: UUID
    catalog_id: UUID
    source_type: ImportSourceType = ImportSourceType.SPREADSHEET


class CatalogImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    catalog_id: UUID
    actor_id: UUID
    source_type: ImportSourceType
    status: ImportStatus
    original_filename: str | None
    spreadsheet_checksum: str | None
    spreadsheet_content_type: str | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    successful_rows: int
    failed_rows: int
    error_count: int
    warning_count: int
    started_at: datetime | None
    validated_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class CatalogImportListResponse(BaseModel):
    items: list[CatalogImportResponse]
    page: PageMetadata


class CatalogImportRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    import_id: UUID
    row_number: int
    action: ImportRowAction
    status: ImportRowStatus
    normalized_data: dict[str, object]
    product_id: UUID | None
    variant_id: UUID | None
    price_id: UUID | None
    inventory_id: UUID | None


class CatalogImportRowsResponse(BaseModel):
    items: list[CatalogImportRowResponse]


class CatalogImportErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    import_id: UUID
    row_id: UUID | None
    row_number: int | None
    field: str | None
    code: str
    message: str
    severity: ImportErrorSeverity
    created_at: datetime


class CatalogImportErrorListResponse(BaseModel):
    items: list[CatalogImportErrorResponse]
    page: PageMetadata


class CatalogImportMediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    import_id: UUID
    filename: str
    content_type: str
    checksum_sha256: str
    file_size: int
    width: int
    height: int
    created_at: datetime


class CatalogImportPreviewResponse(BaseModel):
    catalog_import: CatalogImportResponse
    total_rows: int
    valid_rows: int
    invalid_rows: int
    error_count: int
    warning_count: int
