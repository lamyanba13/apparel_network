from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain.media import ProductMedia
from app.modules.products.infrastructure.media_models import ProductMediaModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.access import store_accessible_by
from app.modules.stores.infrastructure.persistence.models import StoreModel


class ProductMediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def product_owned(
        self, product_id: UUID, owner_id: UUID
    ) -> ProductMediaModel | None:
        return cast(
            ProductMediaModel | None,
            await self.session.scalar(
                select(ProductModel).where(
                    ProductModel.id == product_id,
                    ProductModel.deleted_at.is_(None),
                    ProductModel.store_id.in_(
                        select(ProductModel.store_id).where(
                            ProductModel.id == product_id
                        )
                    ),
                )
            ),
        )

    async def get_product(
        self, product_id: UUID, owner_id: UUID
    ) -> ProductModel | None:
        return cast(
            ProductModel | None,
            await self.session.scalar(
                select(ProductModel)
                .join(StoreModel, StoreModel.id == ProductModel.store_id)
                .where(
                    ProductModel.id == product_id,
                    store_accessible_by(owner_id),
                    ProductModel.deleted_at.is_(None),
                )
            ),
        )

    async def variant_in_product(
        self, product_id: UUID, variant_id: UUID, owner_id: UUID
    ) -> bool:
        return (
            await self.session.scalar(
                select(ProductVariantModel.id)
                .join(StoreModel, StoreModel.id == ProductVariantModel.store_id)
                .where(
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.deleted_at.is_(None),
                    store_accessible_by(owner_id),
                )
            )
            is not None
        )

    async def add(self, values: dict[str, object]) -> ProductMedia:
        model = ProductMediaModel(**values)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return to_domain(model)

    async def list(self, product_id: UUID) -> Sequence[ProductMedia]:
        rows = (
            await self.session.scalars(
                select(ProductMediaModel)
                .where(
                    ProductMediaModel.product_id == product_id,
                    ProductMediaModel.deleted_at.is_(None),
                )
                .order_by(ProductMediaModel.display_order, ProductMediaModel.created_at)
            )
        ).all()
        return [to_domain(row) for row in rows]

    async def get(self, product_id: UUID, media_id: UUID) -> ProductMedia | None:
        row = await self.session.scalar(
            select(ProductMediaModel).where(
                ProductMediaModel.product_id == product_id,
                ProductMediaModel.id == media_id,
                ProductMediaModel.deleted_at.is_(None),
            )
        )
        return to_domain(row) if row else None

    async def archive_primary(self, product_id: UUID) -> None:
        await self.session.execute(
            update(ProductMediaModel)
            .where(
                ProductMediaModel.product_id == product_id,
                ProductMediaModel.role == "primary",
                ProductMediaModel.is_active.is_(True),
                ProductMediaModel.deleted_at.is_(None),
            )
            .values(
                is_active=False,
                deleted_at=func.now(),
                version=ProductMediaModel.version + 1,
            )
        )
        await self.session.flush()

    async def soft_delete(
        self, product_id: UUID, media_id: UUID, version: int
    ) -> ProductMedia | None:
        row = await self.session.scalar(
            select(ProductMediaModel).where(
                ProductMediaModel.product_id == product_id,
                ProductMediaModel.id == media_id,
                ProductMediaModel.version == version,
                ProductMediaModel.deleted_at.is_(None),
            )
        )
        if row is None:
            return None
        row.is_active = False
        row.deleted_at = datetime.utcnow()
        row.version += 1
        await self.session.flush()
        return to_domain(row)


def to_domain(row: ProductMediaModel) -> ProductMedia:
    return ProductMedia(
        **{field: getattr(row, field) for field in ProductMedia.__dataclass_fields__}
    )
