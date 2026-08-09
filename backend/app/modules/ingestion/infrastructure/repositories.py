from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.domain import CatalogStatus
from app.modules.catalogs.domain.taxonomy import CategoryStatus, CollectionStatus
from app.modules.catalogs.infrastructure.models import CatalogModel
from app.modules.catalogs.infrastructure.taxonomy_models import (
    CategoryModel,
    CollectionModel,
    CollectionProductModel,
    ProductCategoryModel,
)
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
from app.modules.ingestion.infrastructure.models import (
    CatalogImportErrorModel,
    CatalogImportMediaModel,
    CatalogImportModel,
    CatalogImportRowModel,
)
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.pricing.domain import PriceStatus
from app.modules.pricing.infrastructure.models import ProductPriceModel
from app.modules.products.domain import AttributeStatus
from app.modules.products.infrastructure.attribute_models import (
    ProductAttributeModel,
    ProductAttributeValueModel,
    ProductVariantAttributeValueModel,
)
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.access import store_accessible_by
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyCatalogImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_catalog_accessible(
        self, store_id: UUID, catalog_id: UUID, actor_id: UUID
    ) -> bool:
        query = (
            select(CatalogModel.id)
            .join(StoreModel, StoreModel.id == CatalogModel.store_id)
            .where(
                StoreModel.id == store_id,
                CatalogModel.id == catalog_id,
                CatalogModel.deleted_at.is_(None),
                CatalogModel.status != CatalogStatus.ARCHIVED,
                store_accessible_by(actor_id),
            )
        )
        return await self._session.scalar(query) is not None

    async def get_by_idempotency(
        self, store_id: UUID, idempotency_key: str, actor_id: UUID
    ) -> CatalogImport | None:
        model = await self._session.scalar(
            select(CatalogImportModel)
            .join(StoreModel, StoreModel.id == CatalogImportModel.store_id)
            .where(
                CatalogImportModel.store_id == store_id,
                CatalogImportModel.idempotency_key == idempotency_key,
                store_accessible_by(actor_id),
            )
        )
        return _import(model) if model else None

    async def add_import(self, values: Mapping[str, object]) -> CatalogImport:
        model = CatalogImportModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _import(model)

    async def get_import(
        self, import_id: UUID, actor_id: UUID, *, lock: bool = False
    ) -> CatalogImport | None:
        query = (
            select(CatalogImportModel)
            .join(StoreModel, StoreModel.id == CatalogImportModel.store_id)
            .where(
                CatalogImportModel.id == import_id,
                store_accessible_by(actor_id),
            )
        )
        if lock:
            query = query.with_for_update(of=CatalogImportModel)
        model = await self._session.scalar(query)
        return _import(model) if model else None

    async def list_imports(
        self, actor_id: UUID, filters: CatalogImportFilter
    ) -> tuple[Sequence[CatalogImport], int]:
        query = (
            select(CatalogImportModel)
            .join(StoreModel, StoreModel.id == CatalogImportModel.store_id)
            .where(store_accessible_by(actor_id))
        )
        if filters.store_id is not None:
            query = query.where(CatalogImportModel.store_id == filters.store_id)
        if filters.status is not None:
            query = query.where(CatalogImportModel.status == filters.status)
        if filters.source_type is not None:
            query = query.where(CatalogImportModel.source_type == filters.source_type)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        models = (
            await self._session.scalars(
                query.order_by(
                    CatalogImportModel.created_at.desc(), CatalogImportModel.id.desc()
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_import(model) for model in models], total

    async def update_import(
        self, import_id: UUID, values: Mapping[str, object]
    ) -> CatalogImport:
        model = await self._session.get(CatalogImportModel, import_id)
        if model is None:
            raise RuntimeError("Catalog Import disappeared during its transaction.")
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _import(model)

    async def spreadsheet_checksum_exists(
        self, store_id: UUID, checksum: str, *, exclude_import_id: UUID
    ) -> bool:
        return (
            await self._session.scalar(
                select(CatalogImportModel.id).where(
                    CatalogImportModel.store_id == store_id,
                    CatalogImportModel.spreadsheet_checksum == checksum,
                    CatalogImportModel.id != exclude_import_id,
                )
            )
            is not None
        )

    async def replace_rows(
        self, import_id: UUID, rows: Sequence[Mapping[str, object]]
    ) -> Sequence[CatalogImportRow]:
        await self._session.execute(
            delete(CatalogImportErrorModel).where(
                CatalogImportErrorModel.import_id == import_id
            )
        )
        await self._session.execute(
            delete(CatalogImportRowModel).where(
                CatalogImportRowModel.import_id == import_id
            )
        )
        models = [
            CatalogImportRowModel(import_id=import_id, **dict(row)) for row in rows
        ]
        self._session.add_all(models)
        await self._session.flush()
        return [_row(model) for model in models]

    async def list_rows(self, import_id: UUID) -> Sequence[CatalogImportRow]:
        models = (
            await self._session.scalars(
                select(CatalogImportRowModel)
                .where(CatalogImportRowModel.import_id == import_id)
                .order_by(CatalogImportRowModel.row_number)
            )
        ).all()
        return [_row(model) for model in models]

    async def update_row(
        self, row_id: UUID, values: Mapping[str, object]
    ) -> CatalogImportRow:
        model = await self._session.get(CatalogImportRowModel, row_id)
        if model is None:
            raise RuntimeError("Catalog Import row disappeared.")
        for key, value in values.items():
            setattr(model, key, value)
        await self._session.flush()
        await self._session.refresh(model)
        return _row(model)

    async def replace_errors(
        self, import_id: UUID, errors: Sequence[Mapping[str, object]]
    ) -> Sequence[CatalogImportError]:
        await self._session.execute(
            delete(CatalogImportErrorModel).where(
                CatalogImportErrorModel.import_id == import_id
            )
        )
        models = [
            CatalogImportErrorModel(import_id=import_id, **dict(error))
            for error in errors
        ]
        self._session.add_all(models)
        await self._session.flush()
        return [_error(model) for model in models]

    async def list_errors(
        self, import_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[CatalogImportError], int]:
        query = select(CatalogImportErrorModel).where(
            CatalogImportErrorModel.import_id == import_id
        )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        models = (
            await self._session.scalars(
                query.order_by(
                    CatalogImportErrorModel.row_number.asc().nullsfirst(),
                    CatalogImportErrorModel.id,
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [_error(model) for model in models], total

    async def add_media(self, values: Mapping[str, object]) -> CatalogImportMedia:
        model = CatalogImportMediaModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _media(model)

    async def list_media(self, import_id: UUID) -> Sequence[CatalogImportMedia]:
        models = (
            await self._session.scalars(
                select(CatalogImportMediaModel)
                .where(CatalogImportMediaModel.import_id == import_id)
                .order_by(CatalogImportMediaModel.filename)
            )
        ).all()
        return [_media(model) for model in models]

    async def media_by_filename(
        self, import_id: UUID, filename: str
    ) -> CatalogImportMedia | None:
        model = await self._session.scalar(
            select(CatalogImportMediaModel).where(
                CatalogImportMediaModel.import_id == import_id,
                func.lower(CatalogImportMediaModel.filename) == filename.casefold(),
            )
        )
        return _media(model) if model else None

    async def media_checksum_exists(self, import_id: UUID, checksum: str) -> bool:
        return (
            await self._session.scalar(
                select(CatalogImportMediaModel.id).where(
                    CatalogImportMediaModel.import_id == import_id,
                    CatalogImportMediaModel.checksum_sha256 == checksum,
                )
            )
            is not None
        )

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        async with self._session.begin_nested():
            yield


class SqlAlchemyCanonicalCatalogReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def product_by_sku(self, store_id: UUID, sku: str) -> ProductMatch | None:
        model = await self._session.scalar(
            select(ProductModel).where(
                ProductModel.store_id == store_id,
                ProductModel.sku == sku,
                ProductModel.deleted_at.is_(None),
            )
        )
        if model is None:
            return None
        return ProductMatch(
            model.id,
            model.catalog_id,
            model.name,
            model.slug,
            model.description,
            model.brand,
            model.version,
        )

    async def variant_by_reference(
        self, store_id: UUID, reference: str
    ) -> VariantMatch | None:
        model = await self._session.scalar(
            select(ProductVariantModel).where(
                ProductVariantModel.store_id == store_id,
                ProductVariantModel.reference == reference,
                ProductVariantModel.deleted_at.is_(None),
            )
        )
        if model is None:
            return None
        rows = (
            await self._session.execute(
                select(ProductAttributeModel.slug, ProductAttributeValueModel.value)
                .select_from(ProductVariantAttributeValueModel)
                .join(
                    ProductAttributeValueModel,
                    ProductAttributeValueModel.id
                    == ProductVariantAttributeValueModel.attribute_value_id,
                )
                .join(
                    ProductAttributeModel,
                    ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
                )
                .where(ProductVariantAttributeValueModel.variant_id == model.id)
            )
        ).all()
        return VariantMatch(
            model.id,
            model.product_id,
            model.reference,
            {row.slug: row.value for row in rows},
            model.version,
        )

    async def category_id(self, store_id: UUID, value: str) -> UUID | None:
        return cast(
            UUID | None,
            await self._session.scalar(
                select(CategoryModel.id).where(
                    CategoryModel.store_id == store_id,
                    CategoryModel.status != CategoryStatus.ARCHIVED,
                    CategoryModel.deleted_at.is_(None),
                    or_(
                        func.lower(CategoryModel.slug) == value.casefold(),
                        func.lower(CategoryModel.name) == value.casefold(),
                    ),
                )
            ),
        )

    async def collection_id(self, store_id: UUID, value: str) -> UUID | None:
        return cast(
            UUID | None,
            await self._session.scalar(
                select(CollectionModel.id).where(
                    CollectionModel.store_id == store_id,
                    CollectionModel.status != CollectionStatus.ARCHIVED,
                    CollectionModel.deleted_at.is_(None),
                    or_(
                        func.lower(CollectionModel.slug) == value.casefold(),
                        func.lower(CollectionModel.name) == value.casefold(),
                    ),
                )
            ),
        )

    async def product_has_category(self, product_id: UUID, category_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(ProductCategoryModel.product_id).where(
                    ProductCategoryModel.product_id == product_id,
                    ProductCategoryModel.category_id == category_id,
                )
            )
            is not None
        )

    async def product_has_collection(
        self, product_id: UUID, collection_id: UUID
    ) -> bool:
        return (
            await self._session.scalar(
                select(CollectionProductModel.product_id).where(
                    CollectionProductModel.product_id == product_id,
                    CollectionProductModel.collection_id == collection_id,
                )
            )
            is not None
        )

    async def attributes_exist(
        self, store_id: UUID, attributes: Mapping[str, str]
    ) -> bool:
        for slug, value in attributes.items():
            found = await self._session.scalar(
                select(ProductAttributeValueModel.id)
                .join(
                    ProductAttributeModel,
                    ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
                )
                .where(
                    ProductAttributeModel.store_id == store_id,
                    ProductAttributeModel.slug == slug,
                    ProductAttributeModel.status == AttributeStatus.ACTIVE,
                    ProductAttributeModel.deleted_at.is_(None),
                    func.lower(ProductAttributeValueModel.value) == value.casefold(),
                )
            )
            if found is None:
                return False
        return True

    async def price_for_variant(
        self, variant_id: UUID, currency: str
    ) -> PriceMatch | None:
        model = await self._session.scalar(
            select(ProductPriceModel)
            .where(
                ProductPriceModel.variant_id == variant_id,
                ProductPriceModel.currency_code == currency,
                ProductPriceModel.status != PriceStatus.ARCHIVED,
                ProductPriceModel.deleted_at.is_(None),
            )
            .order_by(ProductPriceModel.created_at.desc())
            .limit(1)
        )
        return (
            PriceMatch(model.id, Decimal(model.base_price), model.version)
            if model
            else None
        )

    async def inventory_for_variant(self, variant_id: UUID) -> InventoryMatch | None:
        model = await self._session.scalar(
            select(InventoryItemModel).where(
                InventoryItemModel.variant_id == variant_id,
                InventoryItemModel.deleted_at.is_(None),
            )
        )
        return (
            InventoryMatch(model.id, model.quantity_on_hand, model.version)
            if model
            else None
        )


def _import(model: CatalogImportModel) -> CatalogImport:
    return CatalogImport(
        id=model.id,
        store_id=model.store_id,
        catalog_id=model.catalog_id,
        actor_id=model.actor_id,
        source_type=model.source_type,
        status=model.status,
        idempotency_key=model.idempotency_key,
        request_fingerprint=model.request_fingerprint,
        original_filename=model.original_filename,
        spreadsheet_checksum=model.spreadsheet_checksum,
        spreadsheet_content_type=model.spreadsheet_content_type,
        total_rows=model.total_rows,
        valid_rows=model.valid_rows,
        invalid_rows=model.invalid_rows,
        successful_rows=model.successful_rows,
        failed_rows=model.failed_rows,
        error_count=model.error_count,
        warning_count=model.warning_count,
        started_at=model.started_at,
        validated_at=model.validated_at,
        completed_at=model.completed_at,
        failed_at=model.failed_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def _row(model: CatalogImportRowModel) -> CatalogImportRow:
    return CatalogImportRow(
        id=model.id,
        import_id=model.import_id,
        row_number=model.row_number,
        fingerprint=model.fingerprint,
        normalized_data=cast(dict[str, JsonValue], model.normalized_data),
        action=model.action,
        status=model.status,
        product_id=model.product_id,
        variant_id=model.variant_id,
        price_id=model.price_id,
        inventory_id=model.inventory_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _error(model: CatalogImportErrorModel) -> CatalogImportError:
    return CatalogImportError(
        id=model.id,
        import_id=model.import_id,
        row_id=model.row_id,
        row_number=model.row_number,
        field=model.field,
        code=model.code,
        message=model.message,
        severity=model.severity,
        created_at=model.created_at,
    )


def _media(model: CatalogImportMediaModel) -> CatalogImportMedia:
    return CatalogImportMedia(
        id=model.id,
        import_id=model.import_id,
        filename=model.filename,
        content_type=model.content_type,
        checksum_sha256=model.checksum_sha256,
        file_size=model.file_size,
        width=model.width,
        height=model.height,
        bucket=model.bucket,
        object_key=model.object_key,
        created_at=model.created_at,
    )
