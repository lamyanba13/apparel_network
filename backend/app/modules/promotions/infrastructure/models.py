from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    AuditFieldsMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.promotions.domain import (
    PromotionStatus,
    PromotionType,
    RuleCondition,
)


class PromotionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "promotions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("priority >= 0", name="priority_non_negative"),
        CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="percentage_range",
        ),
        CheckConstraint(
            "fixed_amount IS NULL OR fixed_amount >= 0",
            name="fixed_amount_non_negative",
        ),
        CheckConstraint(
            "maximum_discount IS NULL OR maximum_discount >= 0",
            name="maximum_discount_non_negative",
        ),
        CheckConstraint(
            "minimum_order_amount IS NULL OR minimum_order_amount >= 0",
            name="minimum_order_non_negative",
        ),
        CheckConstraint(
            "minimum_quantity IS NULL OR minimum_quantity > 0",
            name="minimum_quantity_positive",
        ),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"
        ),
        CheckConstraint(
            "per_customer_usage_limit IS NULL OR per_customer_usage_limit > 0",
            name="customer_usage_limit_positive",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'", name="deleted_archived"
        ),
        Index("ix_promotions_store", "store_id"),
        Index("ix_promotions_store_status", "store_id", "status"),
        Index("ix_promotions_effective", "effective_from", "effective_until"),
        Index("ix_promotions_priority", "priority"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    promotion_type: Mapped[PromotionType] = mapped_column(
        Enum(
            PromotionType,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[PromotionStatus] = mapped_column(
        Enum(
            PromotionStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        default=PromotionStatus.DRAFT,
        server_default=PromotionStatus.DRAFT.value,
        nullable=False,
    )
    currency: Mapped[str | None] = mapped_column(String(3))
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    buy_quantity: Mapped[int | None]
    get_quantity: Mapped[int | None]
    bundle_quantity: Mapped[int | None]
    bundle_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    tiers: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    first_purchase_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    customer_group: Mapped[str | None] = mapped_column(String(50))
    minimum_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    minimum_quantity: Mapped[int | None]
    maximum_discount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    usage_limit: Mapped[int | None]
    per_customer_usage_limit: Mapped[int | None]
    exclusive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    stackable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    priority: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    maximum_stack: Mapped[int | None]
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PromotionRuleModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "promotion_rules"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_promotion_rules_promotion", "promotion_id"),
        Index("ix_promotion_rules_condition", "condition"),
    )

    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False
    )
    condition: Mapped[RuleCondition] = mapped_column(
        Enum(
            RuleCondition,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PromotionCouponModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "promotion_coupons"
    __table_args__ = (
        UniqueConstraint("store_id", "code", name="uq_promotion_coupons_store_code"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"
        ),
        CheckConstraint(
            "per_customer_usage_limit IS NULL OR per_customer_usage_limit > 0",
            name="customer_usage_limit_positive",
        ),
        Index("ix_promotion_coupons_promotion", "promotion_id"),
        Index("ix_promotion_coupons_store", "store_id"),
        Index("ix_promotion_coupons_active", "store_id", "active"),
    )

    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int | None]
    per_customer_usage_limit: Mapped[int | None]
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PromotionRedemptionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (
        UniqueConstraint(
            "checkout_session_id",
            "promotion_id",
            name="uq_promotion_redemptions_checkout_promotion",
        ),
        CheckConstraint("discount_amount >= 0", name="discount_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_promotion_redemptions_promotion", "promotion_id"),
        Index("ix_promotion_redemptions_coupon", "coupon_id"),
        Index("ix_promotion_redemptions_customer", "customer_id"),
        Index("ix_promotion_redemptions_store", "store_id"),
        Index("ix_promotion_redemptions_checkout", "checkout_session_id"),
        Index("ix_promotion_redemptions_order", "order_id"),
    )

    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id", ondelete="RESTRICT"), nullable=False
    )
    coupon_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("promotion_coupons.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_carts.id", ondelete="RESTRICT"), nullable=False
    )
    checkout_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT")
    )
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(64))
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PromotionCustomerUsageModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "promotion_customer_usage"
    __table_args__ = (
        UniqueConstraint(
            "promotion_id",
            "coupon_id",
            "customer_id",
            name="uq_promotion_customer_usage_scope",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("usage_count >= 0", name="usage_count_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_promotion_customer_usage_promotion", "promotion_id"),
        Index("ix_promotion_customer_usage_customer", "customer_id"),
        Index("ix_promotion_customer_usage_store", "store_id"),
    )

    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False
    )
    coupon_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("promotion_coupons.id", ondelete="CASCADE")
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    usage_count: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)
