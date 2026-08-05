from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.cart.api.dependencies import build_cart_service
from app.modules.promotions.application.services import (
    CouponService,
    PromotionEvaluationService,
    PromotionOutboxService,
    PromotionService,
)
from app.modules.promotions.infrastructure.repositories import (
    SqlAlchemyPromotionCouponRepository,
    SqlAlchemyPromotionOutboxRepository,
    SqlAlchemyPromotionRedemptionRepository,
    SqlAlchemyPromotionRepository,
    SqlAlchemyPromotionRuleRepository,
)


def build_promotion_service(session: AsyncSession) -> PromotionService:
    return PromotionService(
        SqlAlchemyPromotionRepository(session),
        SqlAlchemyPromotionRuleRepository(session),
        PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(session)),
    )


def build_coupon_service(session: AsyncSession) -> CouponService:
    return CouponService(
        SqlAlchemyPromotionCouponRepository(session),
        build_promotion_service(session),
        PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(session)),
    )


def build_promotion_evaluation_service(
    request: Request, session: AsyncSession
) -> PromotionEvaluationService:
    return PromotionEvaluationService(
        SqlAlchemyPromotionRepository(session),
        SqlAlchemyPromotionRuleRepository(session),
        SqlAlchemyPromotionCouponRepository(session),
        SqlAlchemyPromotionRedemptionRepository(session),
        build_cart_service(request, session),
        PromotionOutboxService(SqlAlchemyPromotionOutboxRepository(session)),
    )


async def promotion_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PromotionService]:
    service = build_promotion_service(session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def coupon_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[CouponService]:
    service = build_coupon_service(session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def promotion_evaluation_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PromotionEvaluationService]:
    service = build_promotion_evaluation_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


PromotionServiceDependency = Annotated[
    PromotionService, Depends(promotion_service_dependency)
]
CouponServiceDependency = Annotated[CouponService, Depends(coupon_service_dependency)]
PromotionEvaluationServiceDependency = Annotated[
    PromotionEvaluationService, Depends(promotion_evaluation_service_dependency)
]
