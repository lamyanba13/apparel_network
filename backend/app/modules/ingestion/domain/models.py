from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue


class ImportSourceType(StrEnum):
    POS = "pos"
    MANUAL = "manual"
    PLATFORM_STAFF = "platform_staff"
    SPREADSHEET = "spreadsheet"


class ImportStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROCESSING = "processing"
    COMPLETED = "completed"
    VALIDATION_FAILED = "validation_failed"
    FAILED = "failed"


class ImportRowAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"
    CONFLICT = "conflict"
    ERROR = "error"


class ImportRowStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportErrorSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class CatalogImport:
    id: UUID
    store_id: UUID
    catalog_id: UUID
    actor_id: UUID
    source_type: ImportSourceType
    status: ImportStatus
    idempotency_key: str
    request_fingerprint: str
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


@dataclass(frozen=True, slots=True)
class CatalogImportRow:
    id: UUID
    import_id: UUID
    row_number: int
    fingerprint: str
    normalized_data: dict[str, JsonValue]
    action: ImportRowAction
    status: ImportRowStatus
    product_id: UUID | None
    variant_id: UUID | None
    price_id: UUID | None
    inventory_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogImportError:
    id: UUID
    import_id: UUID
    row_id: UUID | None
    row_number: int | None
    field: str | None
    code: str
    message: str
    severity: ImportErrorSeverity
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogImportMedia:
    id: UUID
    import_id: UUID
    filename: str
    content_type: str
    checksum_sha256: str
    file_size: int
    width: int
    height: int
    bucket: str
    object_key: str
    created_at: datetime
