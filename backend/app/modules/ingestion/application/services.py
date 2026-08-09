from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.catalogs.application.taxonomy_services import (
    CategoryService,
    CollectionService,
)
from app.modules.ingestion.application.media import validate_image
from app.modules.ingestion.application.parsers import (
    ParsedError,
    SpreadsheetParser,
    safe_filename,
)
from app.modules.ingestion.application.repositories import (
    CanonicalCatalogReader,
    CatalogImportRepository,
)
from app.modules.ingestion.application.schemas import (
    CatalogImportCreate,
    CatalogImportFilter,
    PreviewSummary,
)
from app.modules.ingestion.domain import (
    CatalogImport,
    CatalogImportCompleted,
    CatalogImportCreated,
    CatalogImportError,
    CatalogImportFailed,
    CatalogImportMedia,
    CatalogImportRow,
    CatalogImportValidated,
    ImportErrorSeverity,
    ImportRowAction,
    ImportRowStatus,
    ImportStatus,
)
from app.modules.inventory.application.schemas import (
    InventoryCreate,
    InventoryReconciliation,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryStatus, TrackingPolicy
from app.modules.pricing.application.schemas import (
    ProductPriceCreate,
    ProductPriceUpdate,
)
from app.modules.pricing.application.services import PricingService
from app.modules.pricing.domain import PriceStatus
from app.modules.products.application.media_services import ProductMediaService
from app.modules.products.application.schemas import ProductCreate, ProductUpdate
from app.modules.products.application.services import ProductService
from app.modules.products.application.variant_schemas import (
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.application.variant_services import ProductVariantService
from app.modules.products.domain import ProductStatus, ProductVisibility
from app.modules.products.domain.media import ProductMediaRole
from app.modules.stores.application.media_storage import StorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)
from app.observability.metrics import (
    CATALOG_IMPORT_DURATION,
    CATALOG_IMPORT_IMAGE_FAILURES,
    CATALOG_IMPORT_ROWS_PROCESSED,
    CATALOG_IMPORT_ROWS_REJECTED,
    CATALOG_IMPORTS_COMPLETED,
    CATALOG_IMPORTS_CREATED,
    CATALOG_IMPORTS_FAILED,
    CATALOG_IMPORTS_VALIDATED,
)

_PARSER_ERROR_CODES = {
    "duplicate_variant_sku",
    "empty_spreadsheet",
    "formula_not_allowed",
    "inconsistent_product",
    "invalid_attributes",
    "invalid_currency",
    "invalid_image_reference",
    "invalid_metadata",
    "invalid_operation",
    "invalid_price",
    "invalid_quantity",
    "invalid_sku",
    "required",
    "unknown_columns",
}


class CatalogImportService:
    def __init__(
        self,
        repository: CatalogImportRepository,
        reader: CanonicalCatalogReader,
        product_service: ProductService,
        variant_service: ProductVariantService,
        pricing_service: PricingService,
        inventory_service: InventoryService,
        category_service: CategoryService,
        collection_service: CollectionService,
        product_media_service: ProductMediaService,
        storage: StorageProvider,
        storage_transaction: StoreMediaStorageTransaction,
        events: EventPublisher,
        bucket: str,
    ) -> None:
        self._repository = repository
        self._reader = reader
        self._products = product_service
        self._variants = variant_service
        self._pricing = pricing_service
        self._inventory = inventory_service
        self._categories = category_service
        self._collections = collection_service
        self._product_media = product_media_service
        self._storage = storage
        self._storage_transaction = storage_transaction
        self._events = events
        self._bucket = bucket
        self._parser = SpreadsheetParser()

    async def create(self, values: CatalogImportCreate) -> CatalogImport:
        fingerprint = _request_fingerprint(values)
        existing = await self._repository.get_by_idempotency(
            values.store_id, values.idempotency_key, values.actor_id
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise _conflict(
                    "The Idempotency-Key belongs to another Catalog Import request."
                )
            return existing
        if not await self._repository.store_catalog_accessible(
            values.store_id, values.catalog_id, values.actor_id
        ):
            raise _not_found()
        result = await self._repository.add_import(
            {
                "store_id": values.store_id,
                "catalog_id": values.catalog_id,
                "actor_id": values.actor_id,
                "source_type": values.source_type,
                "status": ImportStatus.CREATED,
                "idempotency_key": values.idempotency_key,
                "request_fingerprint": fingerprint,
            }
        )
        CATALOG_IMPORTS_CREATED.inc()
        await self._publish(CatalogImportCreated, result)
        return result

    async def get(self, import_id: UUID, actor_id: UUID) -> CatalogImport:
        value = await self._repository.get_import(import_id, actor_id)
        if value is None:
            raise _not_found()
        return value

    async def list_imports(
        self, actor_id: UUID, filters: CatalogImportFilter
    ) -> tuple[Sequence[CatalogImport], int]:
        return await self._repository.list_imports(actor_id, filters)

    async def errors(
        self, import_id: UUID, actor_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[CatalogImportError], int]:
        await self.get(import_id, actor_id)
        return await self._repository.list_errors(import_id, offset=offset, limit=limit)

    async def rows(self, import_id: UUID, actor_id: UUID) -> Sequence[CatalogImportRow]:
        await self.get(import_id, actor_id)
        return await self._repository.list_rows(import_id)

    async def upload_spreadsheet(
        self,
        import_id: UUID,
        actor_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> CatalogImport:
        value = await self._locked(import_id, actor_id)
        if value.status not in {
            ImportStatus.CREATED,
            ImportStatus.VALIDATION_FAILED,
        }:
            raise _conflict("The Catalog Import cannot accept another spreadsheet.")
        try:
            parsed = self._parser.parse(filename, content_type, data)
        except ValueError as error:
            raise _validation("file", str(error), "invalid_spreadsheet") from error
        if await self._repository.spreadsheet_checksum_exists(
            value.store_id,
            parsed.checksum_sha256,
            exclude_import_id=value.id,
        ):
            raise _conflict("This spreadsheet was already uploaded for this Store.")
        rows = await self._repository.replace_rows(
            value.id,
            [
                {
                    "row_number": row.row_number,
                    "fingerprint": row.fingerprint,
                    "normalized_data": row.data,
                    "action": ImportRowAction.SKIP,
                    "status": ImportRowStatus.PENDING,
                }
                for row in parsed.rows
            ],
        )
        row_ids = {row.row_number: row.id for row in rows}
        await self._repository.replace_errors(
            value.id,
            [_parsed_error(error, row_ids) for error in parsed.errors],
        )
        invalid_rows = len(
            {
                error.row_number
                for error in parsed.errors
                if error.row_number is not None
            }
        )
        total_rows = len(rows) + invalid_rows
        return await self._repository.update_import(
            value.id,
            {
                "status": ImportStatus.CREATED,
                "original_filename": safe_filename(filename),
                "spreadsheet_checksum": parsed.checksum_sha256,
                "spreadsheet_content_type": content_type[:150] or None,
                "total_rows": total_rows,
                "valid_rows": 0,
                "invalid_rows": invalid_rows,
                "successful_rows": 0,
                "failed_rows": 0,
                "error_count": len(parsed.errors),
                "warning_count": 0,
                "started_at": None,
                "validated_at": None,
                "completed_at": None,
                "failed_at": None,
            },
        )

    async def upload_media(
        self,
        import_id: UUID,
        actor_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> CatalogImportMedia:
        value = await self._locked(import_id, actor_id)
        if value.status not in {
            ImportStatus.CREATED,
            ImportStatus.VALIDATION_FAILED,
        }:
            raise _conflict("The Catalog Import cannot accept additional media.")
        try:
            image = validate_image(filename, content_type, data)
        except ValueError as error:
            CATALOG_IMPORT_IMAGE_FAILURES.inc()
            raise _validation("file", str(error), "invalid_image") from error
        if await self._repository.media_by_filename(value.id, image.filename):
            raise _conflict("An image with this filename already exists in the Import.")
        if await self._repository.media_checksum_exists(
            value.id, image.checksum_sha256
        ):
            raise _conflict("This image already exists in the Import.")
        object_key = f"catalog-imports/{value.id}/{uuid7()}{image.extension}"
        stored = await self._storage_transaction.upload(
            self._bucket,
            object_key,
            image.data,
            content_type=image.content_type,
        )
        return await self._repository.add_media(
            {
                "import_id": value.id,
                "filename": image.filename,
                "content_type": image.content_type,
                "checksum_sha256": image.checksum_sha256,
                "file_size": len(image.data),
                "width": image.width,
                "height": image.height,
                "bucket": stored.bucket,
                "object_key": stored.object_key,
            }
        )

    async def validate(
        self, import_id: UUID, actor_id: UUID
    ) -> tuple[CatalogImport, PreviewSummary]:
        value = await self._locked(import_id, actor_id)
        if value.status in {ImportStatus.PROCESSING, ImportStatus.COMPLETED}:
            raise _conflict(
                "The Catalog Import cannot be validated in its current state."
            )
        if value.spreadsheet_checksum is None:
            raise _validation(
                "file", "Upload a spreadsheet before validation.", "missing_spreadsheet"
            )
        await self._repository.update_import(
            value.id,
            {"status": ImportStatus.VALIDATING, "started_at": datetime.now(UTC)},
        )
        rows = await self._repository.list_rows(value.id)
        parse_errors, _ = await self._repository.list_errors(
            value.id, offset=0, limit=10_000
        )
        errors: list[dict[str, object]] = [
            {
                "row_id": error.row_id,
                "row_number": error.row_number,
                "field": error.field,
                "code": error.code,
                "message": error.message,
                "severity": error.severity,
            }
            for error in parse_errors
            if error.code in _PARSER_ERROR_CODES
        ]
        valid_rows = 0
        invalid_rows = len(
            {
                error.row_number
                for error in parse_errors
                if error.row_number is not None and error.code in _PARSER_ERROR_CODES
            }
        )
        image_owners: dict[str, str] = {}
        for row in rows:
            row_errors, action, enriched = await self._validate_row(
                value, row, image_owners
            )
            if row_errors:
                invalid_rows += 1
                errors.extend(row_errors)
                await self._repository.update_row(
                    row.id,
                    {
                        "action": (
                            ImportRowAction.CONFLICT
                            if any(
                                error["code"] == "canonical_conflict"
                                for error in row_errors
                            )
                            else ImportRowAction.ERROR
                        ),
                        "status": ImportRowStatus.INVALID,
                    },
                )
            else:
                valid_rows += 1
                await self._repository.update_row(
                    row.id,
                    {
                        "action": action,
                        "status": ImportRowStatus.VALID,
                        "normalized_data": enriched,
                    },
                )
        await self._repository.replace_errors(value.id, errors)
        error_count = sum(
            1 for error in errors if error["severity"] == ImportErrorSeverity.ERROR
        )
        warning_count = len(errors) - error_count
        failed = error_count > 0
        updated = await self._repository.update_import(
            value.id,
            {
                "status": (
                    ImportStatus.VALIDATION_FAILED if failed else ImportStatus.VALIDATED
                ),
                "valid_rows": valid_rows,
                "invalid_rows": invalid_rows,
                "error_count": error_count,
                "warning_count": warning_count,
                "validated_at": None if failed else datetime.now(UTC),
                "failed_at": datetime.now(UTC) if failed else None,
            },
        )
        if failed:
            CATALOG_IMPORTS_FAILED.inc()
            CATALOG_IMPORT_ROWS_REJECTED.inc(invalid_rows)
            await self._publish(CatalogImportFailed, updated)
        else:
            CATALOG_IMPORTS_VALIDATED.inc()
            await self._publish(CatalogImportValidated, updated)
        return updated, PreviewSummary(
            total_rows=updated.total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            error_count=error_count,
            warning_count=warning_count,
        )

    async def commit(self, import_id: UUID, actor_id: UUID) -> CatalogImport:
        value = await self._locked(import_id, actor_id)
        if value.status is ImportStatus.COMPLETED:
            return value
        if value.status is not ImportStatus.VALIDATED:
            raise _conflict("Only a validated Catalog Import can be committed.")
        processing = await self._repository.update_import(
            value.id,
            {"status": ImportStatus.PROCESSING, "started_at": datetime.now(UTC)},
        )
        rows = await self._repository.list_rows(value.id)
        products: dict[str, UUID] = {}
        categorized: set[tuple[UUID, UUID]] = set()
        collected: set[tuple[UUID, UUID]] = set()
        uploaded_images: set[tuple[UUID, str]] = set()
        current_row: CatalogImportRow | None = None
        try:
            async with self._repository.savepoint():
                for current_row in rows:
                    result = await self._commit_row(
                        processing,
                        current_row,
                        products,
                        categorized,
                        collected,
                        uploaded_images,
                    )
                    await self._repository.update_row(
                        current_row.id,
                        {
                            **result,
                            "status": ImportRowStatus.COMPLETED,
                        },
                    )
        except AppError as error:
            await self._storage_transaction.rollback()
            if current_row is not None:
                await self._repository.update_row(
                    current_row.id,
                    {"status": ImportRowStatus.FAILED, "action": ImportRowAction.ERROR},
                )
            await self._repository.replace_errors(
                value.id,
                [
                    {
                        "row_id": current_row.id if current_row else None,
                        "row_number": current_row.row_number if current_row else None,
                        "field": None,
                        "code": "canonical_commit_failed",
                        "message": error.detail,
                        "severity": ImportErrorSeverity.ERROR,
                    }
                ],
            )
            failed = await self._repository.update_import(
                value.id,
                {
                    "status": ImportStatus.FAILED,
                    "failed_rows": 1,
                    "error_count": 1,
                    "failed_at": datetime.now(UTC),
                },
            )
            CATALOG_IMPORTS_FAILED.inc()
            CATALOG_IMPORT_ROWS_REJECTED.inc()
            await self._publish(CatalogImportFailed, failed)
            return failed
        completed = await self._repository.update_import(
            value.id,
            {
                "status": ImportStatus.COMPLETED,
                "successful_rows": len(rows),
                "failed_rows": 0,
                "completed_at": datetime.now(UTC),
            },
        )
        CATALOG_IMPORTS_COMPLETED.inc()
        CATALOG_IMPORT_ROWS_PROCESSED.inc(len(rows))
        if completed.started_at is not None and completed.completed_at is not None:
            CATALOG_IMPORT_DURATION.observe(
                (completed.completed_at - completed.started_at).total_seconds()
            )
        await self._publish(CatalogImportCompleted, completed)
        return completed

    async def _validate_row(
        self,
        catalog_import: CatalogImport,
        row: CatalogImportRow,
        image_owners: dict[str, str],
    ) -> tuple[list[dict[str, object]], ImportRowAction, dict[str, JsonValue]]:
        data = dict(row.normalized_data)
        errors: list[dict[str, object]] = []
        product_sku = _text(data, "product_sku")
        variant_sku = _text(data, "variant_sku")
        operation = _text(data, "operation")
        category_id = await self._reader.category_id(
            catalog_import.store_id, _text(data, "category")
        )
        if category_id is None:
            errors.append(
                _row_error(
                    row,
                    "category",
                    "unknown_category",
                    "Category was not found for this Store.",
                )
            )
        collection_id: UUID | None = None
        if data.get("collection"):
            collection_id = await self._reader.collection_id(
                catalog_import.store_id, _text(data, "collection")
            )
            if collection_id is None:
                errors.append(
                    _row_error(
                        row,
                        "collection",
                        "unknown_collection",
                        "Collection was not found for this Store.",
                    )
                )
        attributes = _string_mapping(data, "attributes")
        if not await self._reader.attributes_exist(catalog_import.store_id, attributes):
            errors.append(
                _row_error(
                    row,
                    "attributes",
                    "unknown_attribute_value",
                    "Every attribute must map to an active Store value.",
                )
            )
        for filename in _string_list(data, "image_references"):
            media = await self._repository.media_by_filename(
                catalog_import.id, filename
            )
            if media is None:
                errors.append(
                    _row_error(
                        row,
                        "image_references",
                        "missing_image",
                        f"Image {filename} is not uploaded.",
                    )
                )
                continue
            owner = image_owners.setdefault(filename.casefold(), product_sku)
            if owner != product_sku:
                errors.append(
                    _row_error(
                        row,
                        "image_references",
                        "ambiguous_image",
                        "One staged image cannot belong to multiple Products.",
                    )
                )
        product = await self._reader.product_by_sku(
            catalog_import.store_id, product_sku
        )
        variant = await self._reader.variant_by_reference(
            catalog_import.store_id, variant_sku
        )
        if product is not None and product.catalog_id != catalog_import.catalog_id:
            errors.append(
                _row_error(
                    row,
                    "product_sku",
                    "canonical_conflict",
                    "Product SKU belongs to another Catalog.",
                )
            )
        if variant is not None and (
            product is None or variant.product_id != product.id
        ):
            errors.append(
                _row_error(
                    row,
                    "variant_sku",
                    "canonical_conflict",
                    "Variant SKU belongs to another Product.",
                )
            )
        if operation == "create" and (product is not None or variant is not None):
            errors.append(
                _row_error(
                    row,
                    "operation",
                    "canonical_conflict",
                    "CREATE conflicts with an existing canonical SKU.",
                )
            )
        if operation == "update" and (product is None or variant is None):
            errors.append(
                _row_error(
                    row,
                    "operation",
                    "canonical_conflict",
                    "UPDATE requires an existing Product and Variant.",
                )
            )
        price = (
            await self._reader.price_for_variant(variant.id, _text(data, "currency"))
            if variant
            else None
        )
        inventory = (
            await self._reader.inventory_for_variant(variant.id) if variant else None
        )
        product_changed = product is not None and any(
            (
                product.name != _text(data, "product_name"),
                product.description != _optional(data, "description"),
                product.brand != _optional(data, "brand"),
            )
        )
        variant_changed = variant is not None and {
            key.casefold(): item.casefold() for key, item in variant.attributes.items()
        } != {key.casefold(): item.casefold() for key, item in attributes.items()}
        amount = Decimal(_text(data, "price"))
        price_changed = price is not None and price.base_price != amount
        quantity = _integer(data, "quantity_on_hand")
        inventory_changed = (
            inventory is not None and inventory.quantity_on_hand != quantity
        )
        canonical: dict[str, JsonValue] = {
            "product_id": str(product.id) if product else None,
            "product_version": product.version if product else None,
            "variant_id": str(variant.id) if variant else None,
            "variant_version": variant.version if variant else None,
            "price_id": str(price.id) if price else None,
            "price_version": price.version if price else None,
            "inventory_id": str(inventory.id) if inventory else None,
            "inventory_version": inventory.version if inventory else None,
            "product_changed": product_changed,
            "variant_changed": variant_changed,
            "price_changed": price_changed,
            "inventory_changed": inventory_changed,
            "category_id": str(category_id) if category_id else None,
            "collection_id": str(collection_id) if collection_id else None,
            "has_category": (
                await self._reader.product_has_category(product.id, category_id)
                if product and category_id
                else False
            ),
            "has_collection": (
                await self._reader.product_has_collection(product.id, collection_id)
                if product and collection_id
                else False
            ),
        }
        data["_canonical"] = canonical
        if errors:
            return errors, ImportRowAction.ERROR, data
        changed = any(
            (
                product is None,
                variant is None,
                price is None,
                inventory is None,
                product_changed,
                variant_changed,
                price_changed,
                inventory_changed,
            )
        )
        action = (
            ImportRowAction.CREATE
            if product is None or variant is None
            else ImportRowAction.UPDATE if changed else ImportRowAction.SKIP
        )
        return [], action, data

    async def _commit_row(
        self,
        catalog_import: CatalogImport,
        row: CatalogImportRow,
        products: dict[str, UUID],
        categorized: set[tuple[UUID, UUID]],
        collected: set[tuple[UUID, UUID]],
        uploaded_images: set[tuple[UUID, str]],
    ) -> dict[str, object]:
        data = row.normalized_data
        canonical = cast(dict[str, JsonValue], data["_canonical"])
        product_sku = _text(data, "product_sku")
        product_id = products.get(product_sku)
        product_created = False
        if product_id is None and canonical.get("product_id"):
            product_id = UUID(str(canonical["product_id"]))
            if canonical.get("product_changed"):
                product = await self._products.update_owned(
                    product_id,
                    catalog_import.actor_id,
                    ProductUpdate(
                        _product_changes(data),
                        int(cast(int, canonical["product_version"])),
                        catalog_import.actor_id,
                    ),
                )
                product_id = product.id
        elif product_id is None:
            product = await self._products.create(
                ProductCreate(
                    catalog_id=catalog_import.catalog_id,
                    name=_text(data, "product_name"),
                    slug=_slug(_text(data, "product_name"), product_sku),
                    short_description=None,
                    description=_optional(data, "description"),
                    status=ProductStatus.DRAFT,
                    visibility=ProductVisibility.PRIVATE,
                    sku=product_sku,
                    brand=_optional(data, "brand"),
                    sort_order=0,
                    actor_id=catalog_import.actor_id,
                )
            )
            product_id = product.id
            product_created = True
        products[product_sku] = product_id
        category_id = UUID(str(canonical["category_id"]))
        category_key = (product_id, category_id)
        if not canonical.get("has_category") and category_key not in categorized:
            await self._categories.assign(
                category_id, product_id, catalog_import.actor_id
            )
            categorized.add(category_key)
        if canonical.get("collection_id"):
            collection_id = UUID(str(canonical["collection_id"]))
            collection_key = (product_id, collection_id)
            if not canonical.get("has_collection") and collection_key not in collected:
                await self._collections.assign(
                    collection_id, product_id, catalog_import.actor_id
                )
                collected.add(collection_key)
        attributes = _string_mapping(data, "attributes")
        if canonical.get("variant_id"):
            variant_id = UUID(str(canonical["variant_id"]))
            if canonical.get("variant_changed"):
                updated_variant = await self._variants.update_owned(
                    variant_id,
                    product_id,
                    catalog_import.actor_id,
                    ProductVariantUpdate(
                        {"attributes": attributes},
                        int(cast(int, canonical["variant_version"])),
                        catalog_import.actor_id,
                    ),
                )
                variant_id = updated_variant.id
        else:
            variant = await self._variants.create(
                product_id,
                ProductVariantCreate(
                    reference=_text(data, "variant_sku"),
                    attributes=attributes,
                    sort_order=0,
                    actor_id=catalog_import.actor_id,
                ),
            )
            variant_id = variant.id
        amount = Decimal(_text(data, "price"))
        if canonical.get("price_id"):
            price_id = UUID(str(canonical["price_id"]))
            price = await self._pricing.get_owned(price_id, catalog_import.actor_id)
            if canonical.get("price_changed"):
                price = await self._pricing.update_owned(
                    price_id,
                    catalog_import.actor_id,
                    ProductPriceUpdate(
                        {"base_price": amount},
                        int(cast(int, canonical["price_version"])),
                        catalog_import.actor_id,
                    ),
                )
        else:
            price = await self._pricing.create(
                ProductPriceCreate(
                    store_id=catalog_import.store_id,
                    product_id=product_id,
                    variant_id=variant_id,
                    currency_code=_text(data, "currency"),
                    base_price=amount,
                    sale_price=None,
                    compare_at_price=None,
                    cost_price=None,
                    tax_class="standard",
                    status=PriceStatus.DRAFT,
                    effective_from=None,
                    effective_until=None,
                    actor_id=catalog_import.actor_id,
                )
            )
        quantity = _integer(data, "quantity_on_hand")
        if canonical.get("inventory_id"):
            inventory_id = UUID(str(canonical["inventory_id"]))
            inventory = await self._inventory.get_owned(
                inventory_id, catalog_import.actor_id
            )
            if canonical.get("inventory_changed"):
                inventory = await self._inventory.reconcile_owned(
                    inventory_id,
                    catalog_import.actor_id,
                    InventoryReconciliation(
                        physical_count=quantity,
                        reason="Catalog Import stock reconciliation",
                        expected_version=int(cast(int, canonical["inventory_version"])),
                        actor_id=catalog_import.actor_id,
                        source="catalog_import",
                        reference_id=catalog_import.id,
                    ),
                )
        else:
            inventory = await self._inventory.create(
                InventoryCreate(
                    variant_id=variant_id,
                    quantity_on_hand=quantity,
                    quantity_reserved=0,
                    status=(
                        InventoryStatus.ACTIVE
                        if quantity > 0
                        else InventoryStatus.OUT_OF_STOCK
                    ),
                    tracking_policy=TrackingPolicy.TRACK,
                    low_stock_threshold=0,
                    actor_id=catalog_import.actor_id,
                )
            )
        for index, filename in enumerate(_string_list(data, "image_references")):
            key = (product_id, filename.casefold())
            if key in uploaded_images:
                continue
            media = await self._repository.media_by_filename(
                catalog_import.id, filename
            )
            if media is None:
                raise _conflict("A validated Import image is no longer available.")
            content = await self._storage.download(media.bucket, media.object_key)
            await self._product_media.upload(
                product_id,
                catalog_import.actor_id,
                (
                    ProductMediaRole.PRIMARY
                    if product_created and index == 0
                    else ProductMediaRole.GALLERY
                ),
                media.filename,
                media.content_type,
                content,
                variant_id=variant_id,
            )
            await self._storage_transaction.stage_delete(media.bucket, media.object_key)
            uploaded_images.add(key)
        return {
            "product_id": product_id,
            "variant_id": variant_id,
            "price_id": price.id,
            "inventory_id": inventory.id,
            "action": row.action,
        }

    async def _locked(self, import_id: UUID, actor_id: UUID) -> CatalogImport:
        value = await self._repository.get_import(import_id, actor_id, lock=True)
        if value is None:
            raise _not_found()
        return value

    async def _publish(
        self,
        event_type: (
            type[CatalogImportCreated]
            | type[CatalogImportValidated]
            | type[CatalogImportCompleted]
            | type[CatalogImportFailed]
        ),
        catalog_import: CatalogImport,
    ) -> None:
        await self._events.publish(
            event_type(
                catalog_import_id=catalog_import.id,
                store_id=catalog_import.store_id,
                version=catalog_import.version,
            )
        )


def _request_fingerprint(values: CatalogImportCreate) -> str:
    data = {
        "store_id": str(values.store_id),
        "catalog_id": str(values.catalog_id),
        "source_type": values.source_type.value,
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _parsed_error(error: ParsedError, row_ids: Mapping[int, UUID]) -> dict[str, object]:
    return {
        "row_id": row_ids.get(error.row_number) if error.row_number else None,
        "row_number": error.row_number,
        "field": error.field,
        "code": error.code,
        "message": error.message,
        "severity": ImportErrorSeverity.ERROR,
    }


def _row_error(
    row: CatalogImportRow, field: str, code: str, message: str
) -> dict[str, object]:
    return {
        "row_id": row.id,
        "row_number": row.row_number,
        "field": field,
        "code": code,
        "message": message,
        "severity": ImportErrorSeverity.ERROR,
    }


def _text(data: Mapping[str, JsonValue], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise RuntimeError(f"Validated Import field {field} is not text.")
    return value


def _integer(data: Mapping[str, JsonValue], field: str) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"Validated Import field {field} is not an integer.")
    return value


def _optional(data: Mapping[str, JsonValue], field: str) -> str | None:
    value = data.get(field)
    return value if isinstance(value, str) else None


def _string_mapping(data: Mapping[str, JsonValue], field: str) -> dict[str, str]:
    value = data.get(field)
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise RuntimeError(f"Validated Import field {field} is not a text mapping.")
    return cast(dict[str, str], value)


def _string_list(data: Mapping[str, JsonValue], field: str) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Validated Import field {field} is not a text list.")
    return cast(list[str], value)


def _product_changes(data: Mapping[str, JsonValue]) -> dict[str, object]:
    return {
        "name": _text(data, "product_name"),
        "description": _optional(data, "description"),
        "brand": _optional(data, "brand"),
    }


def _slug(name: str, sku: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", f"{name}-{sku}".casefold()).strip("-")
    return value[:180].rstrip("-")


def _validation(field: str, message: str, code: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Catalog Import validation failed",
        detail="Catalog Import input is invalid.",
        status_code=422,
        errors=[FieldError(field=field, code=code, message=message)],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Catalog Import not found",
        detail="The requested Catalog Import was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Catalog Import conflict",
        detail=detail,
        status_code=409,
    )
