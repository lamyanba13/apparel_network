from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
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
from app.modules.notifications.domain import NotificationChannel, NotificationStatus


class _Lifecycle(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
):
    __abstract__ = True


class NotificationTemplateModel(_Lifecycle, Base):
    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint(
            "event_name",
            "channel",
            "language",
            name="uq_notification_templates_event_channel_language",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_notification_templates_lookup",
            "event_name",
            "channel",
            "language",
            "active",
        ),
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(10), server_default="en", nullable=False
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)


class NotificationPreferenceModel(_Lifecycle, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_notification_preferences_customer"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_notification_preferences_customer", "customer_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    sms_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    push_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    language: Mapped[str] = mapped_column(
        String(10), server_default="en", nullable=False
    )
    marketing_opt_in: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )


class NotificationModel(_Lifecycle, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "source_event_id",
            "customer_id",
            "channel",
            name="uq_notifications_source_customer_channel",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        CheckConstraint("max_retries >= 0", name="max_retries_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_notifications_customer_status", "customer_id", "status"),
        Index("ix_notifications_store", "store_id"),
        Index("ix_notifications_retry", "status", "next_retry_at"),
        Index("ix_notifications_source_event", "source_event_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT")
    )
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="RESTRICT"), nullable=False
    )
    source_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("event_outbox.id", ondelete="RESTRICT")
    )
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        server_default="pending",
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(server_default="0", nullable=False)
    max_retries: Mapped[int] = mapped_column(server_default="3", nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDeliveryModel(_Lifecycle, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", name="uq_notification_deliveries_notification"
        ),
        CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_notification_deliveries_notification", "notification_id"),
    )
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        nullable=False,
    )
    gateway_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_ms: Mapped[int] = mapped_column(nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class NotificationFailureModel(_Lifecycle, Base):
    __tablename__ = "notification_failures"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "attempt", name="uq_notification_failures_attempt"
        ),
        CheckConstraint("attempt > 0", name="attempt_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_notification_failures_notification", "notification_id"),
    )
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(nullable=False)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    error_detail: Mapped[str] = mapped_column(Text, nullable=False)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
