from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import DomainEvent
from app.modules.catalogs.domain import Catalog
from app.modules.products.application.attribute_schemas import (
    AttributeCreate,
    AttributeValueCreate,
)
from app.modules.products.application.attribute_services import (
    AttributeService,
    OutboxService,
)
from app.modules.products.application.schemas import ProductCreate
from app.modules.products.application.services import ProductService
from app.modules.products.application.variant_schemas import ProductVariantCreate
from app.modules.products.application.variant_services import ProductVariantService
from app.modules.products.domain import (
    AttributeStatus,
    AttributeType,
    Product,
    ProductStatus,
    ProductVariant,
    ProductVisibility,
)
from app.modules.products.infrastructure.attribute_repositories import (
    SqlAlchemyAttributeRepository,
    SqlAlchemyAttributeValueRepository,
    SqlAlchemyOutboxRepository,
)
from app.modules.products.infrastructure.repositories import (
    SqlAlchemyProductRepository,
)
from app.modules.products.infrastructure.variant_repositories import (
    SqlAlchemyProductVariantRepository,
)
from tests.helpers.builders import product_name, slug, variant_reference


class _DiscardingEventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        del event


async def create_product(
    session: AsyncSession,
    catalog: Catalog,
    actor_id: UUID,
    value: int = 1,
) -> Product:
    service = ProductService(
        SqlAlchemyProductRepository(session),
        _DiscardingEventPublisher(),
    )
    return await service.create(
        ProductCreate(
            catalog_id=catalog.id,
            name=product_name(value),
            slug=slug(value, prefix="product"),
            short_description=f"Test product {value}",
            description=f"Integration test product {value}",
            status=ProductStatus.DRAFT,
            visibility=ProductVisibility.PUBLIC,
            sku=f"TEST-SKU-{value}",
            brand="Test Brand",
            sort_order=value,
            actor_id=actor_id,
        )
    )


async def create_product_variant(
    session: AsyncSession,
    product: Product,
    actor_id: UUID,
    value: int = 1,
) -> ProductVariant:
    attributes = AttributeService(
        SqlAlchemyAttributeRepository(session),
        SqlAlchemyAttributeValueRepository(session),
    )
    for order, (name, slug_value, attribute_value, value_slug) in enumerate(
        (
            ("Color", "color", "Black", "black"),
            ("Size", "size", "Medium", "medium"),
        )
    ):
        attribute = await attributes.create(
            AttributeCreate(
                store_id=product.store_id,
                name=name,
                slug=slug_value,
                attribute_type=AttributeType.ENUM,
                description=None,
                required=True,
                filterable=True,
                searchable=True,
                sort_order=order,
                status=AttributeStatus.ACTIVE,
                actor_id=actor_id,
            )
        )
        await attributes.create_value(
            attribute.id,
            actor_id,
            AttributeValueCreate(
                value=attribute_value,
                slug=value_slug,
                sort_order=0,
                actor_id=actor_id,
            ),
        )
    service = ProductVariantService(
        SqlAlchemyProductVariantRepository(session),
        OutboxService(SqlAlchemyOutboxRepository(session)),
    )
    return await service.create(
        product.id,
        ProductVariantCreate(
            reference=variant_reference(value),
            attributes={"color": "Black", "size": "Medium"},
            sort_order=value,
            actor_id=actor_id,
        ),
    )


@pytest.fixture
async def product(db_session: AsyncSession, catalog: Catalog) -> Product:
    assert catalog.created_by_id is not None
    return await create_product(db_session, catalog, catalog.created_by_id)


@pytest.fixture
async def product_variant(
    db_session: AsyncSession,
    product: Product,
) -> ProductVariant:
    assert product.created_by_id is not None
    return await create_product_variant(db_session, product, product.created_by_id)
