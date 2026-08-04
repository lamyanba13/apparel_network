from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
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
from app.modules.payments.domain import (
    PaymentProvider,
    PaymentStatus,
    PaymentTransactionType,
)


class PaymentIntentModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "payment_intents"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "idempotency_key", name="uq_payment_intents_idempotency"
        ),
        UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_intents_provider_ref"
        ),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 16 AND 128",
            name="idempotency_key_length",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status = 'created' AND authorized_at IS NULL AND captured_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'authorized' AND authorized_at IS NOT NULL "
            "AND captured_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'captured' AND authorized_at IS NOT NULL "
            "AND captured_at IS NOT NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'failed' AND captured_at IS NULL AND failed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'cancelled' AND captured_at IS NULL AND failed_at IS NULL "
            "AND cancelled_at IS NOT NULL AND deleted_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        Index("ix_payment_intents_order", "order_id"),
        Index("ix_payment_intents_customer", "customer_id"),
        Index("ix_payment_intents_store", "store_id"),
        Index("ix_payment_intents_status", "status"),
        Index("ix_payment_intents_expires_at", "expires_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(
            PaymentProvider,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=PaymentStatus.CREATED,
        server_default=PaymentStatus.CREATED.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PaymentTransactionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint(
            "provider_transaction_id", name="uq_payment_transactions_provider_id"
        ),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint("event_type = status", name="event_matches_status"),
        Index("ix_payment_transactions_intent", "payment_intent_id"),
        Index("ix_payment_transactions_occurred_at", "occurred_at"),
    )

    payment_intent_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_intents.id", ondelete="CASCADE"), nullable=False
    )
    provider_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[PaymentTransactionType] = mapped_column(
        Enum(
            PaymentTransactionType,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider_payload: Mapped[dict[str, JsonValue]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
