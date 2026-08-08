from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import UuidPrimaryKeyMixin


class EventConsumerReceiptModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "event_consumer_receipts"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "consumer_name",
            name="uq_event_consumer_receipts_event_consumer",
        ),
        Index("ix_event_consumer_receipts_event", "event_id"),
        Index("ix_event_consumer_receipts_consumer", "consumer_name", "processed_at"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_outbox.id", ondelete="RESTRICT"), nullable=False
    )
    consumer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
