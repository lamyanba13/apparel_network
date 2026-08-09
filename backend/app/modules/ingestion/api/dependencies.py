from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.core.config import Settings
from app.database.session import get_db
from app.events import TransactionalOutboxPublisher
from app.modules.catalogs.application.taxonomy_services import (
    CategoryService,
    CollectionService,
)
from app.modules.catalogs.infrastructure.taxonomy_repositories import (
    SqlAlchemyTaxonomyRepository,
)
from app.modules.ingestion.application.services import CatalogImportService
from app.modules.ingestion.infrastructure.repositories import (
    SqlAlchemyCanonicalCatalogReader,
    SqlAlchemyCatalogImportRepository,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryMovementRepository,
    SqlAlchemyInventoryRepository,
)
from app.modules.pricing.application.services import PricingService
from app.modules.pricing.infrastructure.repositories import (
    SqlAlchemyProductPriceRepository,
)
from app.modules.products.application.attribute_services import OutboxService
from app.modules.products.application.media_services import ProductMediaService
from app.modules.products.application.services import ProductService
from app.modules.products.application.variant_services import ProductVariantService
from app.modules.products.infrastructure.attribute_repositories import (
    SqlAlchemyOutboxRepository,
)
from app.modules.products.infrastructure.media_repositories import (
    ProductMediaRepository,
)
from app.modules.products.infrastructure.repositories import SqlAlchemyProductRepository
from app.modules.products.infrastructure.variant_repositories import (
    SqlAlchemyProductVariantRepository,
)
from app.modules.stores.infrastructure.media_storage import MinIOStorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)


async def catalog_import_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[CatalogImportService]:
    settings = cast(Settings, request.app.state.settings)
    secret = (
        settings.s3_secret_access_key.get_secret_value()
        if settings.s3_secret_access_key
        else ""
    )
    if not settings.s3_access_key_id:
        raise RuntimeError("Catalog Import media storage is not configured.")
    storage = MinIOStorageProvider(
        settings.s3_endpoint_url,
        settings.s3_access_key_id,
        secret,
        region=settings.s3_region,
    )
    storage_transaction = StoreMediaStorageTransaction(storage)
    delegate = cast(EventPublisher, request.app.state.store_events)
    outbox = TransactionalOutboxPublisher(session, delegate=delegate)
    taxonomy_repository = SqlAlchemyTaxonomyRepository(session)
    service = CatalogImportService(
        SqlAlchemyCatalogImportRepository(session),
        SqlAlchemyCanonicalCatalogReader(session),
        ProductService(SqlAlchemyProductRepository(session), delegate),
        ProductVariantService(
            SqlAlchemyProductVariantRepository(session),
            OutboxService(SqlAlchemyOutboxRepository(session)),
        ),
        PricingService(SqlAlchemyProductPriceRepository(session), outbox),
        InventoryService(
            SqlAlchemyInventoryRepository(session),
            outbox,
            SqlAlchemyInventoryMovementRepository(session),
        ),
        CategoryService(taxonomy_repository, delegate),
        CollectionService(taxonomy_repository, delegate),
        ProductMediaService(
            ProductMediaRepository(session),
            storage,
            storage_transaction,
            delegate,
            settings.s3_bucket,
            settings.media_presigned_url_expiration_seconds,
        ),
        storage,
        storage_transaction,
        outbox,
        settings.s3_bucket,
    )
    committed = False
    try:
        yield service
        await session.commit()
        committed = True
        await storage_transaction.commit()
    except Exception:
        if not committed:
            await session.rollback()
            await storage_transaction.rollback()
        raise


CatalogImportServiceDependency = Annotated[
    CatalogImportService, Depends(catalog_import_service_dependency)
]
