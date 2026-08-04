from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.products.application.attribute_services import (
    AttributeService,
    OutboxService,
    VariantAttributeService,
)
from app.modules.products.application.services import ProductService
from app.modules.products.application.variant_services import ProductVariantService
from app.modules.products.infrastructure.attribute_repositories import (
    SqlAlchemyAttributeRepository,
    SqlAlchemyAttributeValueRepository,
    SqlAlchemyOutboxRepository,
    SqlAlchemyVariantAttributeRepository,
)
from app.modules.products.infrastructure.repositories import SqlAlchemyProductRepository
from app.modules.products.infrastructure.variant_repositories import (
    SqlAlchemyProductVariantRepository,
)


async def product_service_dependency(
    request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> AsyncIterator[ProductService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield ProductService(SqlAlchemyProductRepository(session), events)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


ProductServiceDependency = Annotated[
    ProductService, Depends(product_service_dependency)
]


async def product_variant_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[ProductVariantService]:
    try:
        yield ProductVariantService(
            SqlAlchemyProductVariantRepository(session),
            OutboxService(SqlAlchemyOutboxRepository(session)),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


ProductVariantServiceDependency = Annotated[
    ProductVariantService, Depends(product_variant_service_dependency)
]


async def attribute_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[AttributeService]:
    try:
        yield AttributeService(
            SqlAlchemyAttributeRepository(session),
            SqlAlchemyAttributeValueRepository(session),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def variant_attribute_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[VariantAttributeService]:
    try:
        yield VariantAttributeService(
            SqlAlchemyVariantAttributeRepository(session),
            OutboxService(SqlAlchemyOutboxRepository(session)),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


AttributeServiceDependency = Annotated[
    AttributeService, Depends(attribute_service_dependency)
]
VariantAttributeServiceDependency = Annotated[
    VariantAttributeService, Depends(variant_attribute_service_dependency)
]
