from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from app.modules.ingestion.application.schemas import (
    CatalogImportFilter,
    InventoryMatch,
    PriceMatch,
    ProductMatch,
    VariantMatch,
)
from app.modules.ingestion.domain import (
    CatalogImport,
    CatalogImportError,
    CatalogImportMedia,
    CatalogImportRow,
)


class CatalogImportRepository(Protocol):
    async def store_catalog_accessible(
        self, store_id: UUID, catalog_id: UUID, actor_id: UUID
    ) -> bool: ...

    async def get_by_idempotency(
        self, store_id: UUID, idempotency_key: str, actor_id: UUID
    ) -> CatalogImport | None: ...

    async def add_import(self, values: Mapping[str, object]) -> CatalogImport: ...

    async def get_import(
        self, import_id: UUID, actor_id: UUID, *, lock: bool = False
    ) -> CatalogImport | None: ...

    async def list_imports(
        self, actor_id: UUID, filters: CatalogImportFilter
    ) -> tuple[Sequence[CatalogImport], int]: ...

    async def update_import(
        self, import_id: UUID, values: Mapping[str, object]
    ) -> CatalogImport: ...

    async def spreadsheet_checksum_exists(
        self, store_id: UUID, checksum: str, *, exclude_import_id: UUID
    ) -> bool: ...

    async def replace_rows(
        self, import_id: UUID, rows: Sequence[Mapping[str, object]]
    ) -> Sequence[CatalogImportRow]: ...

    async def list_rows(self, import_id: UUID) -> Sequence[CatalogImportRow]: ...

    async def update_row(
        self, row_id: UUID, values: Mapping[str, object]
    ) -> CatalogImportRow: ...

    async def replace_errors(
        self, import_id: UUID, errors: Sequence[Mapping[str, object]]
    ) -> Sequence[CatalogImportError]: ...

    async def list_errors(
        self, import_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[CatalogImportError], int]: ...

    async def add_media(self, values: Mapping[str, object]) -> CatalogImportMedia: ...

    async def list_media(self, import_id: UUID) -> Sequence[CatalogImportMedia]: ...

    async def media_by_filename(
        self, import_id: UUID, filename: str
    ) -> CatalogImportMedia | None: ...

    async def media_checksum_exists(self, import_id: UUID, checksum: str) -> bool: ...

    def savepoint(self) -> AbstractAsyncContextManager[None]: ...


class CanonicalCatalogReader(Protocol):
    async def product_by_sku(self, store_id: UUID, sku: str) -> ProductMatch | None: ...

    async def variant_by_reference(
        self, store_id: UUID, reference: str
    ) -> VariantMatch | None: ...

    async def category_id(self, store_id: UUID, value: str) -> UUID | None: ...

    async def collection_id(self, store_id: UUID, value: str) -> UUID | None: ...

    async def product_has_category(
        self, product_id: UUID, category_id: UUID
    ) -> bool: ...

    async def product_has_collection(
        self, product_id: UUID, collection_id: UUID
    ) -> bool: ...

    async def attributes_exist(
        self, store_id: UUID, attributes: Mapping[str, str]
    ) -> bool: ...

    async def price_for_variant(
        self, variant_id: UUID, currency: str
    ) -> PriceMatch | None: ...

    async def inventory_for_variant(
        self, variant_id: UUID
    ) -> InventoryMatch | None: ...
