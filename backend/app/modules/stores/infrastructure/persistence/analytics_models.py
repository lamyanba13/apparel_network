from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UuidPrimaryKeyMixin, VersionNumberMixin
from app.modules.stores.domain.analytics import MetricMetadata, MetricType


class StoreDailyMetricsModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "store_daily_metrics"
    __table_args__ = (
        UniqueConstraint("store_id", "metric_date", name="store_metric_date_unique"),
        CheckConstraint(
            "profile_views >= 0 AND gallery_views >= 0 AND media_uploads >= 0 "
            "AND staff_invitations >= 0 AND staff_acceptances >= 0 "
            "AND verification_submissions >= 0 AND verification_approvals >= 0 "
            "AND verification_rejections >= 0 AND active_members >= 0",
            name="counters_nonnegative",
        ),
        CheckConstraint("storage_bytes >= 0", name="storage_bytes_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_store_daily_metrics_store_id", "store_id"),
        Index("ix_store_daily_metrics_metric_date", "metric_date"),
        Index("ix_store_daily_metrics_store_date", "store_id", "metric_date"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    profile_views: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    gallery_views: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    media_uploads: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    staff_invitations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    staff_acceptances: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    verification_submissions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    verification_approvals: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    verification_rejections: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    storage_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    active_members: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class StoreMetricEventModel(Base):
    __tablename__ = "store_metric_events"
    __table_args__ = (
        Index("ix_store_metric_events_store_id", "store_id"),
        Index("ix_store_metric_events_event_type", "event_type"),
        Index("ix_store_metric_events_occurred_at", "occurred_at"),
        Index("ix_store_metric_events_store_occurred", "store_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[MetricType] = mapped_column(
        Enum(
            MetricType,
            name="store_metric_type",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    metadata_: Mapped[MetricMetadata] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
