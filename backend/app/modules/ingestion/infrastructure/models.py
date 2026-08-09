from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.ingestion.domain import (
    ImportErrorSeverity,
    ImportRowAction,
    ImportRowStatus,
    ImportSourceType,
    ImportStatus,
)


class CatalogImportModel(UuidPrimaryKeyMixin, TimestampMixin, VersionNumberMixin, Base):
    __tablename__ = "catalog_imports"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "idempotency_key", name="uq_catalog_imports_idempotency"
        ),
        CheckConstraint("version >= 1", name="catalog_imports_version_positive"),
        CheckConstraint(
            "total_rows >= 0 AND valid_rows >= 0 AND invalid_rows >= 0 "
            "AND successful_rows >= 0 AND failed_rows >= 0 "
            "AND error_count >= 0 AND warning_count >= 0",
            name="catalog_imports_counts_nonnegative",
        ),
        CheckConstraint(
            "valid_rows + invalid_rows <= total_rows",
            name="catalog_imports_validation_counts_bounded",
        ),
        Index("ix_catalog_imports_store", "store_id"),
        Index("ix_catalog_imports_catalog", "catalog_id"),
        Index("ix_catalog_imports_actor", "actor_id"),
        Index("ix_catalog_imports_status", "status"),
        Index("ix_catalog_imports_source", "source_type"),
        Index("ix_catalog_imports_created", "created_at"),
        Index("ix_catalog_imports_store_created", "store_id", "created_at"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    catalog_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalogs.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[ImportSourceType] = mapped_column(
        Enum(
            ImportSourceType,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[ImportStatus] = mapped_column(
        Enum(
            ImportStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ImportStatus.CREATED,
        server_default=ImportStatus.CREATED.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    spreadsheet_checksum: Mapped[str | None] = mapped_column(String(64))
    spreadsheet_content_type: Mapped[str | None] = mapped_column(String(150))
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    invalid_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    successful_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    failed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogImportRowModel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_import_rows"
    __table_args__ = (
        UniqueConstraint(
            "import_id", "row_number", name="uq_catalog_import_rows_number"
        ),
        Index("ix_catalog_import_rows_import", "import_id"),
        Index("ix_catalog_import_rows_status", "import_id", "status"),
        Index("ix_catalog_import_rows_action", "import_id", "action"),
    )

    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_imports.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    action: Mapped[ImportRowAction] = mapped_column(
        Enum(
            ImportRowAction,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ImportRowAction.SKIP,
        server_default=ImportRowAction.SKIP.value,
    )
    status: Mapped[ImportRowStatus] = mapped_column(
        Enum(
            ImportRowStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ImportRowStatus.PENDING,
        server_default=ImportRowStatus.PENDING.value,
    )
    product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    price_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_prices.id", ondelete="RESTRICT")
    )
    inventory_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT")
    )


class CatalogImportErrorModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "catalog_import_errors"
    __table_args__ = (
        Index("ix_catalog_import_errors_import", "import_id"),
        Index("ix_catalog_import_errors_row", "import_id", "row_number"),
        Index("ix_catalog_import_errors_severity", "import_id", "severity"),
    )

    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_imports.id", ondelete="CASCADE"), nullable=False
    )
    row_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("catalog_import_rows.id", ondelete="CASCADE")
    )
    row_number: Mapped[int | None]
    field: Mapped[str | None] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[ImportErrorSeverity] = mapped_column(
        Enum(
            ImportErrorSeverity,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class CatalogImportMediaModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "catalog_import_media"
    __table_args__ = (
        UniqueConstraint(
            "import_id", "filename", name="uq_catalog_import_media_filename"
        ),
        UniqueConstraint(
            "import_id", "checksum_sha256", name="uq_catalog_import_media_checksum"
        ),
        CheckConstraint("file_size > 0", name="catalog_import_media_size_positive"),
        CheckConstraint(
            "width > 0 AND height > 0", name="catalog_import_media_dimensions_positive"
        ),
        Index("ix_catalog_import_media_import", "import_id"),
        Index("ix_catalog_import_media_checksum", "checksum_sha256"),
    )

    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_imports.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
