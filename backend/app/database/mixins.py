from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, Uuid, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from uuid6 import uuid7


class UuidPrimaryKeyMixin:
    """Provide an application-generated, time-ordered UUIDv7 identifier."""

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )


class TimestampMixin:
    """Provide timezone-aware creation and mutation timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Provide opt-in reversible deletion metadata.

    Approved lifecycle states remain the default for business records. Future models
    may use this mixin only when their deletion workflow explicitly requires it.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AuditFieldsMixin:
    """Provide nullable actor attribution without coupling to a future user model."""

    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class VersionNumberMixin:
    """Provide SQLAlchemy optimistic-lock version tracking."""

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.version}
