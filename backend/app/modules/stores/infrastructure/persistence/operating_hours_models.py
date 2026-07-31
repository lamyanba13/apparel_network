from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)


class StoreOperatingHoursModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "store_operating_hours"
    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="day_of_week_valid",
        ),
        CheckConstraint("priority >= 0", name="priority_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(effective_from IS NULL AND effective_until IS NULL) OR "
            "(effective_from IS NOT NULL AND effective_until IS NOT NULL "
            "AND effective_from < effective_until)",
            name="effective_period_valid",
        ),
        CheckConstraint(
            "(is_closed AND NOT is_24_hours AND opening_time IS NULL "
            "AND closing_time IS NULL) OR "
            "(is_24_hours AND NOT is_closed AND opening_time IS NULL "
            "AND closing_time IS NULL) OR "
            "(NOT is_closed AND NOT is_24_hours AND opening_time IS NOT NULL "
            "AND closing_time IS NOT NULL AND opening_time < closing_time)",
            name="hours_mode_valid",
        ),
        CheckConstraint(
            "char_length(timezone) BETWEEN 1 AND 64",
            name="timezone_length",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 500",
            name="notes_length",
        ),
        Index(
            "ix_store_hours_resolution",
            "store_id",
            "day_of_week",
            "priority",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_store_hours_effective_range",
            "store_id",
            "effective_from",
            "effective_until",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_store_hours_active_store",
            "store_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Kolkata",
        server_default="Asia/Kolkata",
    )
    opening_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    closing_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    is_closed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_24_hours: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
