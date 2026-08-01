from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    AuditFieldsMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.catalogs.domain import CatalogStatus, CatalogVisibility


class CatalogModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "catalogs"
    __table_args__ = (
        UniqueConstraint("store_id", "slug", name="uq_catalogs_store_slug"),
        CheckConstraint("version >= 1", name="catalogs_version_positive"),
        CheckConstraint("sort_order >= 0", name="catalogs_sort_order_non_negative"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="catalogs_deleted_archived",
        ),
        Index("ix_catalogs_store_id", "store_id"),
        Index("ix_catalogs_store_status", "store_id", "status"),
        Index("ix_catalogs_store_visibility", "store_id", "visibility"),
        Index("ix_catalogs_store_sort_order", "store_id", "sort_order"),
        Index("ix_catalogs_slug", "slug"),
        Index(
            "ix_catalogs_default_active",
            "store_id",
            unique=True,
            postgresql_where=text(
                "is_default = true AND status = 'active' AND deleted_at IS NULL"
            ),
        ),
        CheckConstraint(
            "is_default = false OR status = 'active'",
            name="catalogs_default_active",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CatalogStatus] = mapped_column(
        Enum(
            CatalogStatus,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=CatalogStatus.DRAFT,
        server_default=CatalogStatus.DRAFT.value,
        nullable=False,
    )
    visibility: Mapped[CatalogVisibility] = mapped_column(
        Enum(
            CatalogVisibility,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=CatalogVisibility.PRIVATE,
        server_default=CatalogVisibility.PRIVATE.value,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_default: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
